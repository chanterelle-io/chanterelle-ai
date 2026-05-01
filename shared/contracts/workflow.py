from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class WorkflowTrigger(BaseModel):
    task_types: list[str] = []
    keywords: list[str] = []
    domains: list[str] = []
    topic_profile_ids: list[str] = []


class WorkflowScope(BaseModel):
    level: str = "global"  # global | workspace | domain
    workspace_ids: list[str] = []
    domains: list[str] = []


class WorkflowStepFallback(BaseModel):
    description: str
    alternative_tool: str | None = None
    alternative_runtime_type: str | None = None


class WorkflowStep(BaseModel):
    step_id: str
    order: int
    title: str
    description: str
    preferred_tool: str | None = None
    preferred_runtime_type: str | None = None
    input_expectations: list[str] = []
    output_expectations: list[str] = []
    validation_rules: list[str] = []
    is_optional: bool = False
    condition: str | None = None
    fallback: WorkflowStepFallback | None = None


class WorkflowRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    version: str = "1.0.0"
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    title: str | None = None
    description: str | None = None
    triggers: WorkflowTrigger = WorkflowTrigger()
    steps: list[WorkflowStep] = []
    required_skill_ids: list[str] = []
    active_policy_ids: list[str] = []
    output_expectations: list[str] = []
    scope: WorkflowScope = WorkflowScope()
    tags: list[str] = []
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None