"""Request/response models."""
from typing import List, Optional

from pydantic import BaseModel, Field


# ---- Liveness ----
class CreateSessionResponse(BaseModel):
    sessionId: str


class LivenessResultResponse(BaseModel):
    sessionId: str
    status: str
    confidence: float
    isLive: bool
    threshold: float
    # S3 location of the reference image captured during the session.
    referenceImageS3: Optional[str] = None
    auditImagesS3: List[str] = Field(default_factory=list)


# ---- Collection 1:N ----
class SearchMatch(BaseModel):
    userId: str
    similarity: float


class EnrollResponse(BaseModel):
    duplicate: bool
    userId: Optional[str] = None
    faceId: Optional[str] = None
    matches: List[SearchMatch] = Field(default_factory=list)
    message: str


class SearchResponse(BaseModel):
    matched: bool
    threshold: float
    matches: List[SearchMatch] = Field(default_factory=list)


class LivenessEnrollResponse(BaseModel):
    """Combined result: verify liveness on a session, then 1:N de-dup search,
    and (if no duplicate) enroll the reference image as a new user vector."""
    isLive: bool
    livenessConfidence: float
    duplicate: bool
    matches: List[SearchMatch] = Field(default_factory=list)
    enrolledUserId: Optional[str] = None
    enrolledFaceId: Optional[str] = None
    message: str
