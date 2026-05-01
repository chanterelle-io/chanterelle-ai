from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from shared.contracts.artifact import ArtifactEvictionResult, PreservedArtifactInfo
from shared.db import get_engine
from shared.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    messages: list[dict] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class SessionCleanupResult:
    session_id: str
    tracked_artifact_ids: list[str] = field(default_factory=list)
    evicted_artifact_ids: list[str] = field(default_factory=list)
    non_evicted_artifact_ids: list[str] = field(default_factory=list)
    preserved_artifacts: list[PreservedArtifactInfo] = field(default_factory=list)
    reclaimed_bytes: int = 0
    deleted: bool = False
    cleanup_error: str | None = None


class SessionStore:
    """Postgres-backed session store (Phase 2)."""

    def get(self, session_id: str) -> Session | None:
        row = self._fetch_row(session_id)
        if row is None:
            return None
        if self._is_expired(row):
            return None
        return self._row_to_session(row)

    def get_or_create(self, session_id: str) -> Session:
        row = self._fetch_row(session_id)
        now = datetime.now(timezone.utc)

        if row and self._is_expired(row):
            logger.info("Session %s expired; resetting stored conversation state", session_id)
            self._cleanup_session_artifacts(session_id)
            self.delete(session_id)
            row = None

        if row:
            self._touch(session_id, now)
            refreshed = self._fetch_row(session_id)
            if refreshed is not None:
                return self._row_to_session(refreshed)

        return self._create_session(session_id, now)

    def save(self, session: Session) -> None:
        now = datetime.now(timezone.utc)
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE sessions
                    SET messages = :messages,
                        artifact_ids = :artifacts,
                        last_accessed_at = :last_accessed_at,
                        expires_at = :expires_at,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": session.id,
                    "messages": json.dumps(session.messages),
                    "artifacts": json.dumps(session.artifact_ids),
                    "last_accessed_at": now,
                    "expires_at": self._next_expiration(now),
                },
            )
            conn.commit()

    def cleanup_expired_sessions(self, limit: int = 100) -> list[SessionCleanupResult]:
        engine = get_engine()
        cleanup_results: list[SessionCleanupResult] = []
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, artifact_ids FROM sessions
                    WHERE expires_at IS NOT NULL AND expires_at <= NOW()
                    ORDER BY expires_at
                    LIMIT :limit
                """),
                {"limit": limit},
            ).mappings().fetchall()

            if rows:
                for row in rows:
                    session_id = row["id"]
                    tracked_artifact_ids = self._decode_json_list(row.get("artifact_ids"))
                    cleanup_result = SessionCleanupResult(
                        session_id=session_id,
                        tracked_artifact_ids=tracked_artifact_ids,
                        non_evicted_artifact_ids=list(tracked_artifact_ids),
                    )

                    artifact_cleanup = self._cleanup_session_artifacts(session_id, strict=True)
                    if artifact_cleanup is None:
                        cleanup_result.cleanup_error = "Artifact cleanup did not return a result"
                        cleanup_results.append(cleanup_result)
                        continue

                    cleanup_result.evicted_artifact_ids = [
                        item.artifact_id for item in artifact_cleanup.evicted_artifacts
                    ]
                    cleanup_result.non_evicted_artifact_ids = [
                        artifact_id
                        for artifact_id in tracked_artifact_ids
                        if artifact_id not in set(cleanup_result.evicted_artifact_ids)
                    ]
                    cleanup_result.preserved_artifacts = artifact_cleanup.preserved_artifacts
                    cleanup_result.reclaimed_bytes = artifact_cleanup.reclaimed_bytes

                    conn.execute(
                        text("DELETE FROM sessions WHERE id = :id"),
                        {"id": session_id},
                    )
                    cleanup_result.deleted = True
                    cleanup_results.append(cleanup_result)
                conn.commit()

        return cleanup_results

    def expire(self, session_id: str) -> Session | None:
        engine = get_engine()
        now = datetime.now(timezone.utc)
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE sessions
                    SET expires_at = :expires_at,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": session_id,
                    "expires_at": now,
                },
            )
            conn.commit()

        if result.rowcount == 0:
            return None
        row = self._fetch_row(session_id)
        if row is None:
            return None
        return self._row_to_session(row)

    def delete(self, session_id: str) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": session_id})
            conn.commit()

    def _cleanup_session_artifacts(
        self,
        session_id: str,
        strict: bool = False,
    ) -> ArtifactEvictionResult | None:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{settings.artifact_service_url}/artifacts/session-cleanup",
                    params={"session_id": session_id},
                )
                resp.raise_for_status()
                return ArtifactEvictionResult.model_validate(resp.json())
        except Exception as exc:
            logger.warning(
                "Failed to clean up artifacts for expired session %s: %s",
                session_id,
                exc,
            )
            if strict:
                raise
        return None

    def _fetch_row(self, session_id: str):
        engine = get_engine()
        with engine.connect() as conn:
            return conn.execute(
                text("""
                    SELECT id, messages, artifact_ids, created_at, last_accessed_at, expires_at
                    FROM sessions
                    WHERE id = :id
                """),
                {"id": session_id},
            ).mappings().fetchone()

    def _create_session(self, session_id: str, now: datetime) -> Session:
        engine = get_engine()
        expires_at = self._next_expiration(now)
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO sessions (id, last_accessed_at, expires_at)
                    VALUES (:id, :last_accessed_at, :expires_at)
                """),
                {
                    "id": session_id,
                    "last_accessed_at": now,
                    "expires_at": expires_at,
                },
            )
            conn.commit()
        return Session(
            id=session_id,
            created_at=now,
            last_accessed_at=now,
            expires_at=expires_at,
        )

    def _touch(self, session_id: str, now: datetime) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE sessions
                    SET last_accessed_at = :last_accessed_at,
                        expires_at = :expires_at,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": session_id,
                    "last_accessed_at": now,
                    "expires_at": self._next_expiration(now),
                },
            )
            conn.commit()

    def _row_to_session(self, row) -> Session:
        messages_raw = row["messages"]
        messages = json.loads(messages_raw) if isinstance(messages_raw, str) else messages_raw
        artifact_ids = self._decode_json_list(row.get("artifact_ids"))
        return Session(
            id=row["id"],
            messages=messages,
            artifact_ids=artifact_ids,
            created_at=row.get("created_at"),
            last_accessed_at=row.get("last_accessed_at"),
            expires_at=row.get("expires_at"),
        )

    def _decode_json_list(self, raw_value) -> list[str]:
        if raw_value is None:
            return []
        decoded = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        if not decoded:
            return []
        return list(decoded)

    def _is_expired(self, row) -> bool:
        expires_at = row.get("expires_at")
        return expires_at is not None and expires_at <= datetime.now(timezone.utc)

    def _next_expiration(self, now: datetime) -> datetime:
        return now + timedelta(hours=settings.session_ttl_hours)
