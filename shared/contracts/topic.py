from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TopicProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    display_name: str | None = None
    description: str | None = None
    status: str = "active"

    allowed_tool_names: list[str] = []
    allowed_connection_names: list[str] = []
    allowed_runtime_types: list[str] = []

    active_skill_ids: list[str] = []
    active_policy_ids: list[str] = []

    domains: list[str] = []
    tags: list[str] = []

    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserTopicAssignment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topic_profile_id: str
    status: str = "active"

    granted_at: datetime | None = None
    granted_by: str | None = None


class ResolvedTopicContext(BaseModel):
    """The merged result of resolving a user's active topic profiles."""
    profiles: list[TopicProfile] = []
    allowed_tool_names: list[str] = []
    allowed_connection_names: list[str] = []
    allowed_runtime_types: list[str] = []
    active_skill_ids: list[str] = []
    active_policy_ids: list[str] = []
