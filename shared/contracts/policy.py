from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PolicyType(str, Enum):
    EXECUTION_ROUTING = "execution_routing"
    TOOL_SELECTION = "tool_selection"
    VALIDATION = "validation"
    SECURITY = "security"
    WORKFLOW_PREFERENCE = "workflow_preference"
    RESPONSE_REQUIREMENT = "response_requirement"


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class PolicyScope(BaseModel):
    level: str = "global"  # global | workspace | domain | connection
    connection_ids: list[str] = []
    task_types: list[str] = []
    domains: list[str] = []
    topic_profile_ids: list[str] = []


class PolicyCondition(BaseModel):
    # Execution routing conditions
    estimated_row_count_above: int | None = None
    source_types: list[str] = []
    sensitivity_levels: list[str] = []

    # Query analysis conditions (matched against SQL runtime /analyze output)
    max_source_table_rows_above: int | None = None
    query_has_no_where: bool | None = None
    query_has_no_limit: bool | None = None

    # Task/tool conditions
    task_types: list[str] = []
    tool_names: list[str] = []

    # Domain conditions
    domains: list[str] = []
    keywords: list[str] = []


class PolicyEffect(BaseModel):
    # Execution routing effects
    force_execution_mode: str | None = None  # interactive | deferred
    preferred_runtime_type: str | None = None
    denied_runtime_types: list[str] = []
    require_isolated_runtime: bool = False

    # Skill/validation effects
    required_skill_ids: list[str] = []

    # Tool effects
    denied_tool_names: list[str] = []
    required_tool_names: list[str] = []

    # Response effects
    required_response_elements: list[str] = []

    # Approval effects
    require_approval: bool = False
    approval_reason: str | None = None


class PolicyRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: PolicyType
    status: str = "active"
    description: str | None = None
    version: str | None = None

    scope: PolicyScope = PolicyScope()
    condition: PolicyCondition = PolicyCondition()
    effect: PolicyEffect = PolicyEffect()

    priority: int = 0
    tags: list[str] = []

    created_at: datetime | None = None
    updated_at: datetime | None = None


class PolicyEvaluation(BaseModel):
    """Result of evaluating policies against a request context."""
    matched_policies: list[PolicyRecord] = []
    denied_tools: list[str] = []
    required_tools: list[str] = []
    denied_runtimes: list[str] = []
    preferred_runtime: str | None = None
    force_execution_mode: str | None = None
    require_approval: bool = False
    approval_reasons: list[str] = []
