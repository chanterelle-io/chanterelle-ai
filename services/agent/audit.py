from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from shared.contracts.audit import WorkflowAuditEvent
from shared.db import get_engine

logger = logging.getLogger(__name__)


class WorkflowAuditStore:
    """Append-only workflow event store for audit and debugging."""

    def record_event(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
        message_index: int | None = None,
        workflow_trace: list[dict[str, Any]] | None = None,
        workflow_denial_message: str | None = None,
        artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not workflow_trace and not workflow_denial_message:
            return

        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO workflow_audit_events (
                        session_id,
                        user_id,
                        message_index,
                        role,
                        content,
                        workflow_trace,
                        workflow_denial_message,
                        artifact_ids,
                        metadata
                    )
                    VALUES (
                        :session_id,
                        :user_id,
                        :message_index,
                        :role,
                        :content,
                        :workflow_trace,
                        :workflow_denial_message,
                        :artifact_ids,
                        :metadata
                    )
                """),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "message_index": message_index,
                    "role": role,
                    "content": content,
                    "workflow_trace": json.dumps(workflow_trace or []),
                    "workflow_denial_message": workflow_denial_message,
                    "artifact_ids": json.dumps(artifact_ids or []),
                    "metadata": json.dumps(metadata or {}),
                },
            )
            conn.commit()

    def record_session_messages(
        self,
        *,
        session_id: str,
        user_id: str | None,
        messages: list[dict[str, Any]],
        start_index: int,
        artifact_ids: list[str] | None = None,
    ) -> None:
        for offset, message in enumerate(messages[start_index:], start=start_index):
            self.record_event(
                session_id=session_id,
                user_id=user_id,
                message_index=offset,
                role=message.get("role", "assistant"),
                content=message.get("content", ""),
                workflow_trace=message.get("workflow_trace") or [],
                workflow_denial_message=message.get("workflow_denial_message"),
                artifact_ids=artifact_ids or [],
            )

    def list_session_events(self, session_id: str) -> list[WorkflowAuditEvent]:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id,
                           session_id,
                           user_id,
                           message_index,
                           role,
                           content,
                           workflow_trace,
                           workflow_denial_message,
                           artifact_ids,
                           metadata,
                           created_at
                    FROM workflow_audit_events
                    WHERE session_id = :session_id
                    ORDER BY created_at, message_index NULLS LAST
                """),
                {"session_id": session_id},
            ).mappings().fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_events(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[WorkflowAuditEvent]:
        filters = []
        params: dict[str, Any] = {"limit": limit}
        if session_id:
            filters.append("session_id = :session_id")
            params["session_id"] = session_id
        if user_id:
            filters.append("user_id = :user_id")
            params["user_id"] = user_id

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id,
                           session_id,
                           user_id,
                           message_index,
                           role,
                           content,
                           workflow_trace,
                           workflow_denial_message,
                           artifact_ids,
                           metadata,
                           created_at
                    FROM workflow_audit_events
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                params,
            ).mappings().fetchall()
        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> WorkflowAuditEvent:
        return WorkflowAuditEvent(
            id=str(row["id"]),
            session_id=row["session_id"],
            user_id=row.get("user_id"),
            message_index=row.get("message_index"),
            role=row["role"],
            content=row.get("content") or "",
            workflow_trace=self._decode_json(row.get("workflow_trace"), []),
            workflow_denial_message=row.get("workflow_denial_message"),
            artifact_ids=self._decode_json(row.get("artifact_ids"), []),
            metadata=self._decode_json(row.get("metadata"), {}),
            created_at=row.get("created_at"),
        )

    def _decode_json(self, raw_value, default):
        if raw_value is None:
            return default
        if isinstance(raw_value, str):
            return json.loads(raw_value)
        return raw_value
