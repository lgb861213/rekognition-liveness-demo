"""Rekognition Face Liveness + Collection (1:N) service layer.

Flow reference (AWS docs):
  Liveness:  CreateFaceLivenessSession -> (Amplify StartFaceLivenessSession) ->
             GetFaceLivenessSessionResults
  1:N:       CreateCollection -> IndexFaces -> CreateUser -> AssociateFaces ->
             SearchUsersByImage
"""
import uuid
from typing import List, Optional, Tuple

from botocore.exceptions import ClientError

from aws_clients import rekognition_client, s3_client
from config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# Collection bootstrap
# ---------------------------------------------------------------------------
def ensure_collection() -> None:
    """Create the collection if it does not already exist (idempotent)."""
    rek = rekognition_client()
    try:
        rek.create_collection(CollectionId=settings.collection_id)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise


# ---------------------------------------------------------------------------
# Face Liveness
# ---------------------------------------------------------------------------
def create_liveness_session() -> str:
    """Step 1: CreateFaceLivenessSession. Returns SessionId (valid 3 minutes).

    Reference and audit images are written by Rekognition to the configured S3
    bucket (same account + same region as the endpoint)."""
    rek = rekognition_client()
    settings_payload = {
        "AuditImagesLimit": settings.audit_images_limit,
    }
    if settings.liveness_s3_bucket:
        settings_payload["OutputConfig"] = {
            "S3Bucket": settings.liveness_s3_bucket,
            "S3KeyPrefix": settings.liveness_s3_prefix,
        }
    resp = rek.create_face_liveness_session(
        ClientRequestToken=str(uuid.uuid4()),
        Settings=settings_payload,
    )
    return resp["SessionId"]


def get_liveness_results(session_id: str) -> dict:
    """Step 3: GetFaceLivenessSessionResults. Returns confidence + image refs."""
    rek = rekognition_client()
    resp = rek.get_face_liveness_session_results(SessionId=session_id)

    confidence = float(resp.get("Confidence", 0.0))
    status = resp.get("Status", "UNKNOWN")
    is_live = (
        status == "SUCCEEDED"
        and confidence >= settings.liveness_confidence_threshold
    )

    ref_s3 = _s3_uri(resp.get("ReferenceImage"))
    audit_s3 = [
        uri for img in resp.get("AuditImages", []) if (uri := _s3_uri(img))
    ]
    return {
        "sessionId": session_id,
        "status": status,
        "confidence": confidence,
        "isLive": is_live,
        "threshold": settings.liveness_confidence_threshold,
        "referenceImageS3": ref_s3,
        "auditImagesS3": audit_s3,
        "_raw": resp,
    }


def _s3_uri(image: Optional[dict]) -> Optional[str]:
    if not image:
        return None
    s3 = image.get("S3Object")
    if not s3 or not s3.get("Bucket"):
        return None
    return f"s3://{s3['Bucket']}/{s3.get('Name', '')}"


def _reference_image_bytes(results: dict) -> Optional[bytes]:
    """Extract the reference image so we can index/search it in the collection.

    GetFaceLivenessSessionResults returns the reference image either inline as
    raw Bytes or as an S3Object. Handle both."""
    ref = results.get("_raw", {}).get("ReferenceImage")
    if not ref:
        return None
    if ref.get("Bytes"):
        return ref["Bytes"]
    s3 = ref.get("S3Object")
    if s3 and s3.get("Bucket") and s3.get("Name"):
        obj = s3_client().get_object(Bucket=s3["Bucket"], Key=s3["Name"])
        return obj["Body"].read()
    return None


# ---------------------------------------------------------------------------
# Collection 1:N  (user vectors)
# ---------------------------------------------------------------------------
def index_face(image_bytes: bytes, external_image_id: Optional[str] = None) -> str:
    """IndexFaces -> returns the FaceId of the largest detected face."""
    rek = rekognition_client()
    kwargs = dict(
        CollectionId=settings.collection_id,
        Image={"Bytes": image_bytes},
        MaxFaces=1,
        QualityFilter="AUTO",
        DetectionAttributes=[],
    )
    if external_image_id:
        kwargs["ExternalImageId"] = external_image_id
    resp = rek.index_faces(**kwargs)
    records = resp.get("FaceRecords", [])
    if not records:
        raise ValueError("No face detected in image for indexing.")
    return records[0]["Face"]["FaceId"]


def create_user_and_associate(user_id: str, face_id: str) -> None:
    """CreateUser + AssociateFaces (builds the user vector)."""
    rek = rekognition_client()
    try:
        rek.create_user(CollectionId=settings.collection_id, UserId=user_id)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConflictException":
            raise
    rek.associate_faces(
        CollectionId=settings.collection_id,
        UserId=user_id,
        FaceIds=[face_id],
        UserMatchThreshold=settings.user_match_threshold,
    )


def enroll_user(image_bytes: bytes, user_id: Optional[str] = None) -> Tuple[str, str]:
    """Full enrollment: index the face then build a user vector. Returns
    (user_id, face_id)."""
    user_id = user_id or f"user-{uuid.uuid4().hex[:12]}"
    face_id = index_face(image_bytes, external_image_id=user_id)
    create_user_and_associate(user_id, face_id)
    return user_id, face_id


def search_faces_by_image(image_bytes: bytes) -> List[dict]:
    """SearchFacesByImage -> searches FACE vectors (not user vectors).

    Unlike user vectors, face vectors are searchable immediately after
    IndexFaces (no association delay), so this closes the eventual-consistency
    gap when the same person is uploaded again within seconds."""
    rek = rekognition_client()
    try:
        resp = rek.search_faces_by_image(
            CollectionId=settings.collection_id,
            Image={"Bytes": image_bytes},
            FaceMatchThreshold=settings.user_match_threshold,
            MaxFaces=5,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] in (
            "InvalidParameterException",
            "ResourceNotFoundException",
        ):
            return []
        raise
    out = []
    for m in resp.get("FaceMatches", []):
        face = m.get("Face", {})
        out.append({
            "userId": face.get("UserId") or face.get("ExternalImageId") or face.get("FaceId"),
            "similarity": float(m.get("Similarity", 0.0)),
        })
    return out


def enroll_user_deduped(
    image_bytes: bytes, user_id: Optional[str] = None
) -> dict:
    """Check-and-enroll: run 1:N search FIRST; only enroll if the face is not
    already in the collection. Prevents duplicate user vectors when the same
    person is uploaded multiple times.

    Checks BOTH user vectors (SearchUsersByImage) and face vectors
    (SearchFacesByImage). Face vectors are searchable immediately after
    IndexFaces, closing the eventual-consistency gap where a freshly-created
    user vector is not yet searchable within a few seconds."""
    matches = search_users_by_image(image_bytes)
    if not matches:
        # Fallback to face-vector search (immediately consistent).
        matches = search_faces_by_image(image_bytes)
    if matches:
        return {
            "duplicate": True,
            "userId": None,
            "faceId": None,
            "matches": matches,
            "message": (
                f"已存在用户 {matches[0]['userId']}"
                f"（相似度 {matches[0]['similarity']:.2f}%），未重复入库。"
            ),
        }
    uid, fid = enroll_user(image_bytes, user_id)
    return {
        "duplicate": False,
        "userId": uid,
        "faceId": fid,
        "matches": [],
        "message": f"未匹配到已有用户，已入库新用户 {uid}。",
    }


def collection_stats() -> dict:
    """Return face/user counts for the collection (for the UI dashboard)."""
    rek = rekognition_client()
    try:
        desc = rek.describe_collection(CollectionId=settings.collection_id)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return {"collectionId": settings.collection_id, "faceCount": 0,
                    "userCount": 0, "exists": False}
        raise
    # UserCount is not returned by DescribeCollection; count via ListUsers.
    user_count = 0
    paginator = rek.get_paginator("list_users")
    for page in paginator.paginate(CollectionId=settings.collection_id):
        user_count += len(page.get("Users", []))
    return {
        "collectionId": settings.collection_id,
        "faceCount": int(desc.get("FaceCount", 0)),
        "userCount": user_count,
        "exists": True,
    }


def list_users() -> List[dict]:
    """List users in the collection with their associated face IDs."""
    rek = rekognition_client()

    # Map userId -> [faceId, ...]
    faces_by_user: dict = {}
    fpag = rek.get_paginator("list_faces")
    for page in fpag.paginate(CollectionId=settings.collection_id):
        for f in page.get("Faces", []):
            uid = f.get("UserId")
            if uid:
                faces_by_user.setdefault(uid, []).append(f["FaceId"])

    users = []
    upag = rek.get_paginator("list_users")
    for page in upag.paginate(CollectionId=settings.collection_id):
        for u in page.get("Users", []):
            uid = u["UserId"]
            users.append({
                "userId": uid,
                "status": u.get("UserStatus", "UNKNOWN"),
                "faceIds": faces_by_user.get(uid, []),
            })
    return users


def delete_user(user_id: str) -> dict:
    """Delete a user vector and its associated face vectors from the collection."""
    rek = rekognition_client()

    # Find faces linked to this user so we can delete them too.
    face_ids = []
    fpag = rek.get_paginator("list_faces")
    for page in fpag.paginate(CollectionId=settings.collection_id):
        for f in page.get("Faces", []):
            if f.get("UserId") == user_id:
                face_ids.append(f["FaceId"])

    # DeleteUser removes the user vector (and disassociates faces).
    rek.delete_user(CollectionId=settings.collection_id, UserId=user_id)

    # Delete the now-orphaned face vectors so storage/counts are cleaned up.
    deleted_faces = []
    if face_ids:
        resp = rek.delete_faces(
            CollectionId=settings.collection_id, FaceIds=face_ids
        )
        deleted_faces = resp.get("DeletedFaces", [])

    return {"deletedUserId": user_id, "deletedFaceIds": deleted_faces}


def search_users_by_image(image_bytes: bytes) -> List[dict]:
    """SearchUsersByImage -> 1:N. Returns list of {userId, similarity}."""
    rek = rekognition_client()
    try:
        resp = rek.search_users_by_image(
            CollectionId=settings.collection_id,
            Image={"Bytes": image_bytes},
            UserMatchThreshold=settings.user_match_threshold,
            MaxUsers=5,
        )
    except ClientError as e:
        # No face / no match variants -> treat as empty result
        if e.response["Error"]["Code"] in (
            "InvalidParameterException",
            "ResourceNotFoundException",
        ):
            return []
        raise
    return [
        {"userId": m["User"]["UserId"], "similarity": float(m["Similarity"])}
        for m in resp.get("UserMatches", [])
    ]


# ---------------------------------------------------------------------------
# Combined: verify liveness -> 1:N dedup -> enroll if new
# ---------------------------------------------------------------------------
def liveness_verify_and_enroll(session_id: str) -> dict:
    results = get_liveness_results(session_id)
    if not results["isLive"]:
        return {
            "isLive": False,
            "livenessConfidence": results["confidence"],
            "duplicate": False,
            "matches": [],
            "enrolledUserId": None,
            "enrolledFaceId": None,
            "message": (
                f"Liveness check failed (status={results['status']}, "
                f"confidence={results['confidence']:.2f} < "
                f"{results['threshold']})."
            ),
        }

    image_bytes = _reference_image_bytes(results)
    if not image_bytes:
        return {
            "isLive": True,
            "livenessConfidence": results["confidence"],
            "duplicate": False,
            "matches": [],
            "enrolledUserId": None,
            "enrolledFaceId": None,
            "message": "Live, but reference image unavailable for 1:N search.",
        }

    matches = search_users_by_image(image_bytes)
    if not matches:
        matches = search_faces_by_image(image_bytes)
    if matches:
        return {
            "isLive": True,
            "livenessConfidence": results["confidence"],
            "duplicate": True,
            "matches": matches,
            "enrolledUserId": None,
            "enrolledFaceId": None,
            "message": (
                f"Duplicate detected: matched existing user "
                f"{matches[0]['userId']} ({matches[0]['similarity']:.2f}%)."
            ),
        }

    user_id, face_id = enroll_user(image_bytes)
    return {
        "isLive": True,
        "livenessConfidence": results["confidence"],
        "duplicate": False,
        "matches": [],
        "enrolledUserId": user_id,
        "enrolledFaceId": face_id,
        "message": f"Live and unique. Enrolled new user {user_id}.",
    }
