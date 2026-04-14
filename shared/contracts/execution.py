from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ToolInvocation(BaseModel):
    tool_name: str
    operation: str
    payload: dict = {}


class ExecutionTarget(BaseModel):
    connection_id: str | None = None
    connection_name: str | None = None


class ExecutionArtifactInput(BaseModel):
    artifact_id: str
    alias: str | None = None


class ExpectedOutput(BaseModel):
    name: str
    type: str = "table"


class ExecutionRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    tool: ToolInvocation
    target: ExecutionTarget | None = None
    input_artifacts: list[ExecutionArtifactInput] = []
    parameters: dict = {}
    expected_outputs: list[ExpectedOutput] = []


class ExecutionResult(BaseModel):
    execution_id: str
    status: str  # "success" | "error"
    artifact_ids: list[str] = []
    error_message: str | None = None
