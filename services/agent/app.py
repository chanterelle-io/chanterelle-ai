import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from shared.contracts.artifact import PreservedArtifactInfo
from services.agent.llm.claude import ClaudeProvider
from services.agent.orchestrator import Orchestrator
from services.agent.session import SessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Service", version="0.1.0")

llm = ClaudeProvider()
orchestrator = Orchestrator(llm=llm)
sessions = SessionStore()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    artifact_ids: list[str] = []


class SessionResponse(BaseModel):
    session_id: str
    message_count: int
    artifact_ids: list[str]
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None


class SessionCleanupResponse(BaseModel):
    deleted_session_ids: list[str]
    deleted_sessions: list["DeletedSessionCleanupResponse"] = Field(default_factory=list)
    skipped_session_ids: list[str] = Field(default_factory=list)
    skipped_sessions: list["SkippedSessionCleanupResponse"] = Field(default_factory=list)


class DeletedSessionCleanupResponse(BaseModel):
    session_id: str
    tracked_artifact_ids: list[str] = Field(default_factory=list)
    evicted_artifact_ids: list[str] = Field(default_factory=list)
    non_evicted_artifact_ids: list[str] = Field(default_factory=list)
    preserved_artifacts: list[PreservedArtifactInfo] = Field(default_factory=list)
    reclaimed_bytes: int = 0


class SkippedSessionCleanupResponse(BaseModel):
    session_id: str
    tracked_artifact_ids: list[str] = Field(default_factory=list)
    cleanup_error: str


class SessionExpireResponse(BaseModel):
    session_id: str
    expires_at: datetime


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    logger.info("Chat request for session %s (user=%s)", req.session_id, req.user_id)
    result = await orchestrator.handle_message(
        session_id=req.session_id,
        user_message=req.message,
        user_id=req.user_id,
    )
    return ChatResponse(**result)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=session.id,
        message_count=len(session.messages),
        artifact_ids=session.artifact_ids,
        last_accessed_at=session.last_accessed_at,
        expires_at=session.expires_at,
    )


@app.post("/sessions/cleanup", response_model=SessionCleanupResponse)
def cleanup_sessions(limit: int = Query(default=100, ge=1, le=1000)) -> SessionCleanupResponse:
    cleanup_results = sessions.cleanup_expired_sessions(limit=limit)
    deleted_sessions = [
        DeletedSessionCleanupResponse(
            session_id=result.session_id,
            tracked_artifact_ids=result.tracked_artifact_ids,
            evicted_artifact_ids=result.evicted_artifact_ids,
            non_evicted_artifact_ids=result.non_evicted_artifact_ids,
            preserved_artifacts=result.preserved_artifacts,
            reclaimed_bytes=result.reclaimed_bytes,
        )
        for result in cleanup_results
        if result.deleted
    ]
    skipped_sessions = [
        SkippedSessionCleanupResponse(
            session_id=result.session_id,
            tracked_artifact_ids=result.tracked_artifact_ids,
            cleanup_error=result.cleanup_error or "Artifact cleanup failed",
        )
        for result in cleanup_results
        if not result.deleted
    ]
    return SessionCleanupResponse(
        deleted_session_ids=[result.session_id for result in cleanup_results if result.deleted],
        deleted_sessions=deleted_sessions,
        skipped_session_ids=[result.session_id for result in cleanup_results if not result.deleted],
        skipped_sessions=skipped_sessions,
    )


@app.post("/sessions/{session_id}/expire", response_model=SessionExpireResponse)
def expire_session(session_id: str) -> SessionExpireResponse:
    session = sessions.expire(session_id)
    if session is None or session.expires_at is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionExpireResponse(session_id=session.id, expires_at=session.expires_at)
