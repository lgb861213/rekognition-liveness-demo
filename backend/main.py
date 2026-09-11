"""FastAPI backend for the Rekognition Face Liveness + 1:N collection demo.

Endpoints
  GET  /health
  POST /api/liveness/session                 -> create a liveness session
  GET  /api/liveness/session/{id}/result     -> raw liveness result
  POST /api/liveness/session/{id}/verify-enroll -> liveness + 1:N dedup + enroll
  POST /api/collection/enroll                 -> enroll a face from an uploaded image
  POST /api/collection/search                 -> 1:N search from an uploaded image
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import rekognition_service as svc
from config import get_settings
from schemas import (
    CreateSessionResponse,
    EnrollResponse,
    LivenessEnrollResponse,
    LivenessResultResponse,
    SearchMatch,
    SearchResponse,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the collection exists on startup (idempotent).
    try:
        svc.ensure_collection()
    except Exception as e:  # noqa: BLE001 - surface but don't crash on boot
        print(f"[startup] could not ensure collection: {e}")
    yield


app = FastAPI(title="Rekognition Liveness + 1:N Demo", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "region": settings.aws_region,
            "collection": settings.collection_id}


@app.get("/api/collection/stats")
def collection_stats():
    try:
        return svc.collection_stats()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/collection/users")
def list_users():
    try:
        return {"users": svc.list_users()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/collection/users/{user_id}")
def delete_user(user_id: str):
    try:
        return svc.delete_user(user_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ---- Liveness ----
@app.post("/api/liveness/session", response_model=CreateSessionResponse)
def create_session():
    try:
        return CreateSessionResponse(sessionId=svc.create_liveness_session())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/liveness/session/{session_id}/result",
         response_model=LivenessResultResponse)
def liveness_result(session_id: str):
    try:
        r = svc.get_liveness_results(session_id)
        return LivenessResultResponse(**{k: v for k, v in r.items() if k != "_raw"})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/liveness/session/{session_id}/verify-enroll",
          response_model=LivenessEnrollResponse)
def verify_and_enroll(session_id: str):
    try:
        r = svc.liveness_verify_and_enroll(session_id)
        r["matches"] = [SearchMatch(**m) for m in r["matches"]]
        return LivenessEnrollResponse(**r)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ---- Collection 1:N (standalone, for image upload testing) ----
@app.post("/api/collection/enroll", response_model=EnrollResponse)
async def enroll(file: UploadFile = File(...), user_id: str = Form(None)):
    try:
        image_bytes = await file.read()
        r = svc.enroll_user_deduped(image_bytes, user_id)
        r["matches"] = [SearchMatch(**m) for m in r["matches"]]
        return EnrollResponse(**r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/collection/search", response_model=SearchResponse)
async def search(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        matches = svc.search_users_by_image(image_bytes)
        return SearchResponse(
            matched=bool(matches),
            threshold=settings.user_match_threshold,
            matches=[SearchMatch(**m) for m in matches],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
