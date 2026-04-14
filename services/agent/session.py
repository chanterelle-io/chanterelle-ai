from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    messages: list[dict] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)


class SessionStore:
    """In-memory session store. Replace with persistent storage in Phase 2."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(id=session_id)
        return self._sessions[session_id]
