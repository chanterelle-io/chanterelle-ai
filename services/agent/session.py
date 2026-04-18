from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import text

from shared.db import get_engine

logger = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    messages: list[dict] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)


class SessionStore:
    """Postgres-backed session store (Phase 2)."""

    def get_or_create(self, session_id: str) -> Session:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, messages, artifact_ids FROM sessions WHERE id = :id"),
                {"id": session_id},
            ).mappings().fetchone()

            if row:
                messages_raw = row["messages"]
                messages = json.loads(messages_raw) if isinstance(messages_raw, str) else messages_raw
                artifacts_raw = row["artifact_ids"]
                artifact_ids = json.loads(artifacts_raw) if isinstance(artifacts_raw, str) else artifacts_raw
                return Session(id=session_id, messages=messages, artifact_ids=artifact_ids)

            conn.execute(
                text("INSERT INTO sessions (id) VALUES (:id)"),
                {"id": session_id},
            )
            conn.commit()
            return Session(id=session_id)

    def save(self, session: Session) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE sessions
                    SET messages = :messages, artifact_ids = :artifacts, updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": session.id,
                    "messages": json.dumps(session.messages),
                    "artifacts": json.dumps(session.artifact_ids),
                },
            )
            conn.commit()
