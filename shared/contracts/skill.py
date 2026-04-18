from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SkillCategory(str, Enum):
    CONNECTOR = "connector"
    METRIC = "metric"
    WORKFLOW = "workflow"
    DOMAIN = "domain"
    COMPLIANCE = "compliance"


class SkillScope(BaseModel):
    level: str = "global"  # global | workspace | domain | connection | workflow | session
    source_types: list[str] = []
    connection_ids: list[str] = []
    connection_names: list[str] = []
    runtime_types: list[str] = []
    tool_names: list[str] = []
    domains: list[str] = []


class SkillTrigger(BaseModel):
    kind: str  # keyword | source_match | task_match | connection_match
    value: str
    weight: float = 1.0


class SkillInstructions(BaseModel):
    summary: str
    detailed_markdown: str | None = None
    recommended_steps: list[str] = []
    dos: list[str] = []
    donts: list[str] = []
    output_expectations: list[str] = []


class SkillRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: SkillCategory
    status: str = "active"
    title: str | None = None
    description: str | None = None
    scope: SkillScope = SkillScope()
    triggers: list[SkillTrigger] = []
    instructions: SkillInstructions = SkillInstructions(summary="")
    tags: list[str] = []
    created_at: datetime | None = None
