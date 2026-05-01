from __future__ import annotations

import logging
from typing import Any

import httpx

from services.agent.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from services.agent.session import Session, SessionStore
from services.agent.tools.sql_query import SQL_QUERY_TOOL
from services.agent.tools.python_transform import PYTHON_TRANSFORM_TOOL
from services.agent.tools.inspect_artifact import INSPECT_ARTIFACT_TOOL
from services.agent.tools.check_job import CHECK_JOB_STATUS_TOOL
from services.agent.tools.pin_artifact import PIN_ARTIFACT_TOOL
from services.agent.tools.unpin_artifact import UNPIN_ARTIFACT_TOOL
from shared.contracts.connection import ConnectionRecord
from shared.contracts.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionTarget,
    ExecutionArtifactInput,
    ExpectedOutput,
    ToolInvocation,
)
from shared.contracts.skill import SkillRecord
from shared.contracts.topic import ResolvedTopicContext
from shared.contracts.workflow import WorkflowRecord
from shared.settings import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 15

WORKFLOW_TOOL_TO_EXECUTION_TOOL = {
    "query_sql_source": "query_sql",
    "transform_with_python": "python_transform",
}

EXECUTION_TOOL_TO_AGENT_TOOL = {
    "query_sql": "query_sql_source",
    "python_transform": "transform_with_python",
}


class Orchestrator:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.sessions = SessionStore()

    async def handle_message(self, session_id: str, user_message: str, user_id: str | None = None) -> dict:
        session = self.sessions.get_or_create(session_id)

        # Resolve topic context if user_id is provided
        topic_context = None
        if user_id:
            topic_context = await self._fetch_topic_context(user_id)

        # Gather context for the system prompt
        connections = await self._fetch_connections()
        artifacts = await self._fetch_session_artifacts(session_id)

        # Filter connections by topic profile
        if topic_context and topic_context.allowed_connection_names:
            connections = [
                c for c in connections
                if c.name in topic_context.allowed_connection_names
            ]

        connection_names = [c.name for c in connections]
        skills = await self._fetch_skills(connection_names, user_message)
        workflows = await self._fetch_workflows(user_message, topic_context)
        active_skill_ids = sorted(skill.id for skill in skills)
        required_skill_ids = self._collect_required_skill_ids(workflows)
        preferred_tool_names = self._collect_preferred_tool_names(workflows)
        active_policy_ids = self._collect_active_policy_ids(workflows, topic_context)

        # Filter skills by topic profile
        if topic_context and topic_context.active_skill_ids:
            skills = [s for s in skills if s.id in topic_context.active_skill_ids]
            active_skill_ids = sorted(skill.id for skill in skills)

        workflow_trace = self._build_workflow_trace(workflows, skills)

        # Build tool list, filtered by topic profile
        all_tools = [
            SQL_QUERY_TOOL,
            PYTHON_TRANSFORM_TOOL,
            INSPECT_ARTIFACT_TOOL,
            PIN_ARTIFACT_TOOL,
            UNPIN_ARTIFACT_TOOL,
            CHECK_JOB_STATUS_TOOL,
        ]
        if topic_context and topic_context.allowed_tool_names:
            # Always include check_job_status regardless of topic profile
            tools = [
                t for t in all_tools
                if t.name in topic_context.allowed_tool_names or t.name == "check_job_status"
            ]
        else:
            tools = all_tools

        system_prompt = self._build_system_prompt(
            connections,
            artifacts,
            tools,
            skills,
            workflows,
            topic_context,
        )

        # Add user message
        session.messages.append({
            "role": "user",
            "content": user_message,
            "workflow_trace": workflow_trace,
        })

        # Run the tool-use loop
        messages = self._build_llm_messages(session)
        new_artifact_ids: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.llm.chat(system=system_prompt, messages=messages, tools=tools)

            if response.stop_reason == "end_turn" or not response.tool_calls:
                # Done — record assistant response
                session.messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                    "workflow_trace": workflow_trace,
                })
                break

            # Record the assistant message with tool calls (preserve provider data for round-trip)
            assistant_msg = Message(
                role="assistant",
                tool_calls=response.tool_calls,
                _provider_data={"role": "assistant", "content": response._provider_data},
            )
            messages.append(assistant_msg)

            # Execute each tool call
            tool_results: list[ToolResult] = []
            stop_after_tool_result = False
            final_tool_message: str | None = None
            for tc in response.tool_calls:
                result_text, artifact_id, should_stop = await self._execute_tool(
                    session,
                    tc,
                    user_id=user_id,
                    active_skill_ids=active_skill_ids,
                    required_skill_ids=required_skill_ids,
                    preferred_tool_names=preferred_tool_names,
                    active_policy_ids=active_policy_ids,
                    workflow_trace=workflow_trace,
                )
                tool_results.append(ToolResult(tool_call_id=tc.id, content=result_text))
                if artifact_id:
                    new_artifact_ids.append(artifact_id)
                    session.artifact_ids.append(artifact_id)
                if should_stop:
                    stop_after_tool_result = True
                    final_tool_message = result_text
                    break

            if stop_after_tool_result:
                session.messages.append({
                    "role": "assistant",
                    "content": final_tool_message or "Execution has been deferred.",
                    "workflow_trace": workflow_trace,
                    "workflow_denial_message": final_tool_message if final_tool_message else None,
                })
                break

            # Add tool results as a user message
            messages.append(Message(role="user", tool_results=tool_results))

            # Also record in session history for persistence
            session.messages.append({
                "role": "assistant",
                "content": f"[Used tool: {response.tool_calls[0].name}]",
                "workflow_trace": workflow_trace,
            })
        else:
            session.messages.append({
                "role": "assistant",
                "content": "I reached the maximum number of tool steps. Here is what I have so far.",
                "workflow_trace": workflow_trace,
            })

        # Persist session state
        self.sessions.save(session)

        return {
            "session_id": session_id,
            "message": session.messages[-1]["content"],
            "artifact_ids": new_artifact_ids,
            "workflow_trace": workflow_trace,
        }

    # --- Tool execution ---

    async def _execute_tool(
        self,
        session: Session,
        tool_call: ToolCall,
        user_id: str | None = None,
        active_skill_ids: list[str] | None = None,
        required_skill_ids: list[str] | None = None,
        preferred_tool_names: list[str] | None = None,
        active_policy_ids: list[str] | None = None,
        workflow_trace: list[dict[str, object]] | None = None,
    ) -> tuple[str, str | None, bool]:
        if tool_call.name == "query_sql_source":
            return await self._execute_sql_query(
                session,
                tool_call.input,
                user_id=user_id,
                active_skill_ids=active_skill_ids,
                required_skill_ids=required_skill_ids,
                preferred_tool_names=preferred_tool_names,
                active_policy_ids=active_policy_ids,
                workflow_trace=workflow_trace,
            )
        if tool_call.name == "transform_with_python":
            return await self._execute_python_transform(
                session,
                tool_call.input,
                user_id=user_id,
                active_skill_ids=active_skill_ids,
                required_skill_ids=required_skill_ids,
                preferred_tool_names=preferred_tool_names,
                active_policy_ids=active_policy_ids,
                workflow_trace=workflow_trace,
            )
        if tool_call.name == "inspect_artifact":
            return await self._execute_inspect_artifact(session, tool_call.input)
        if tool_call.name == "pin_artifact":
            return await self._execute_pin_artifact(session, tool_call.input)
        if tool_call.name == "unpin_artifact":
            return await self._execute_unpin_artifact(session, tool_call.input)
        if tool_call.name == "check_job_status":
            return await self._execute_check_job_status(session, tool_call.input)
        return f"Unknown tool: {tool_call.name}", None, False

    async def _execute_sql_query(
        self,
        session: Session,
        tool_input: dict,
        user_id: str | None = None,
        active_skill_ids: list[str] | None = None,
        required_skill_ids: list[str] | None = None,
        preferred_tool_names: list[str] | None = None,
        active_policy_ids: list[str] | None = None,
        workflow_trace: list[dict[str, object]] | None = None,
    ) -> tuple[str, str | None, bool]:
        connection_name = tool_input.get("connection_name", "")
        query = tool_input.get("query", "")
        artifact_name = tool_input.get("artifact_name", "query_result")
        estimated_row_count = tool_input.get("estimated_row_count")

        parameters = {}
        if estimated_row_count is not None:
            parameters["estimated_row_count"] = estimated_row_count

        exec_request = ExecutionRequest(
            session_id=session.id,
            user_id=user_id,
            active_skill_ids=active_skill_ids or [],
            required_skill_ids=required_skill_ids or [],
            preferred_tool_names=preferred_tool_names or [],
            active_policy_ids=active_policy_ids or [],
            tool=ToolInvocation(
                tool_name="query_sql",
                operation="query",
                payload={"query": query},
            ),
            target=ExecutionTarget(connection_name=connection_name),
            expected_outputs=[ExpectedOutput(name=artifact_name, type="table")],
            parameters=parameters,
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.execution_service_url}/execute",
                json=exec_request.model_dump(),
            )

        if resp.status_code != 200:
            error_detail = resp.json().get("detail", resp.text)
            return f"Error executing query: {error_detail}", None, False

        result = ExecutionResult(**resp.json())
        if result.status == "error":
            return f"Query failed: {result.error_message}", None, False
        if result.status == "denied":
            denial_message = self._format_workflow_constraint_denial(
                tool_name="query_sql",
                result=result,
                workflow_trace=workflow_trace,
            )
            if denial_message:
                return denial_message, None, True
            return f"Query denied by policy: {result.error_message}", None, False
        if result.status == "deferred":
            return (
                f"This query has been deferred to a background job (job ID: {result.job_id}). "
                f"The query will run asynchronously. Use the check_job_status tool with "
                f"job_id '{result.job_id}' to check when it's done."
            ), None, True

        # Fetch artifact metadata for the summary
        artifact_id = result.artifact_ids[0] if result.artifact_ids else None
        if artifact_id:
            summary = await self._get_artifact_summary(artifact_id)
            return summary, artifact_id, False

        return "Query executed but no artifact was produced.", None, False

    async def _execute_python_transform(
        self,
        session: Session,
        tool_input: dict,
        user_id: str | None = None,
        active_skill_ids: list[str] | None = None,
        required_skill_ids: list[str] | None = None,
        preferred_tool_names: list[str] | None = None,
        active_policy_ids: list[str] | None = None,
        workflow_trace: list[dict[str, object]] | None = None,
    ) -> tuple[str, str | None, bool]:
        code = tool_input.get("code", "")
        input_artifact_names = tool_input.get("input_artifacts", [])
        artifact_name = tool_input.get("artifact_name", "transform_result")

        # Resolve artifact names to IDs
        all_artifacts = await self._fetch_session_artifacts(session.id)
        artifact_map = {a["name"]: a["id"] for a in all_artifacts}
        input_refs = []
        for name in input_artifact_names:
            aid = artifact_map.get(name)
            if not aid:
                return f"Artifact '{name}' not found in this session.", None, False
            input_refs.append(ExecutionArtifactInput(artifact_id=aid, alias=name))

        exec_request = ExecutionRequest(
            session_id=session.id,
            user_id=user_id,
            active_skill_ids=active_skill_ids or [],
            required_skill_ids=required_skill_ids or [],
            preferred_tool_names=preferred_tool_names or [],
            active_policy_ids=active_policy_ids or [],
            tool=ToolInvocation(
                tool_name="python_transform",
                operation="transform",
                payload={"code": code},
            ),
            input_artifacts=input_refs,
            expected_outputs=[ExpectedOutput(name=artifact_name, type="table")],
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.execution_service_url}/execute",
                json=exec_request.model_dump(),
            )

        if resp.status_code != 200:
            error_detail = resp.json().get("detail", resp.text)
            return f"Error executing transform: {error_detail}", None, False

        result = ExecutionResult(**resp.json())
        if result.status == "error":
            return f"Transform failed: {result.error_message}", None, False
        if result.status == "denied":
            denial_message = self._format_workflow_constraint_denial(
                tool_name="python_transform",
                result=result,
                workflow_trace=workflow_trace,
            )
            if denial_message:
                return denial_message, None, True
            return f"Transform denied by policy: {result.error_message}", None, False
        if result.status == "deferred":
            return (
                f"This transform has been deferred to a background job (job ID: {result.job_id}). "
                f"It will run asynchronously. Use the check_job_status tool with "
                f"job_id '{result.job_id}' to check when it's done."
            ), None, True

        artifact_id = result.artifact_ids[0] if result.artifact_ids else None
        if artifact_id:
            summary = await self._get_artifact_summary(artifact_id)
            return summary, artifact_id, False

        return "Transform executed but no artifact was produced.", None, False

    async def _execute_inspect_artifact(
        self, session: Session, tool_input: dict
    ) -> tuple[str, str | None, bool]:
        artifact_name = tool_input.get("artifact_name", "")
        max_rows = min(tool_input.get("max_rows", 5), 20)  # cap at 20

        artifact = await self._resolve_artifact_by_name(session.id, artifact_name)
        if not artifact:
            return f"Artifact '{artifact_name}' not found in this session.", None, False

        artifact_id = artifact["id"]

        # Get metadata
        schema = artifact.get("schema_info") or {}
        columns = schema.get("columns", [])
        stats = artifact.get("statistics") or {}
        row_count = stats.get("row_count", "?")
        preview = artifact.get("preview") or {}
        preview_rows = preview.get("sample_rows") or []

        # Download and read sample rows
        if preview_rows and max_rows <= len(preview_rows):
            sample_str = self._rows_to_csv(preview_rows[:max_rows])
        else:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        f"{settings.artifact_service_url}/artifacts/{artifact_id}/download"
                    )
                    resp.raise_for_status()

                import io
                import pyarrow.parquet as pq

                buf = io.BytesIO(resp.content)
                table = pq.read_table(buf)
                df = table.to_pandas()
                sample = df.head(max_rows)
                sample_str = sample.to_csv(index=False)
            except Exception as e:
                logger.warning("Failed to download artifact for inspection: %s", e)
                sample_str = "(Could not load sample rows)"

        col_details = "\n".join(
            f"  - {c['name']} ({c.get('logical_type', '?')})" for c in columns
        )

        return (
            f"**Artifact: {artifact_name}** ({row_count} rows, {len(columns)} columns)\n\n"
            f"Columns:\n{col_details}\n\n"
            f"Sample rows (first {max_rows}):\n{sample_str}"
        ), None, False

    async def _execute_pin_artifact(
        self, session: Session, tool_input: dict
    ) -> tuple[str, str | None, bool]:
        artifact_name = tool_input.get("artifact_name", "")
        artifact = await self._resolve_artifact_by_name(session.id, artifact_name)
        if not artifact:
            return f"Artifact '{artifact_name}' not found in this session.", None, False

        artifact_id = artifact["id"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.artifact_service_url}/artifacts/{artifact_id}/pin"
                )
                resp.raise_for_status()
            updated = resp.json()
        except Exception as e:
            return f"Error pinning artifact '{artifact_name}': {e}", None, False

        return (
            f"Artifact '{updated.get('name', artifact_name)}' is now pinned and protected from automatic cleanup."
        ), None, False

    async def _execute_unpin_artifact(
        self, session: Session, tool_input: dict
    ) -> tuple[str, str | None, bool]:
        artifact_name = tool_input.get("artifact_name", "")
        artifact = await self._resolve_artifact_by_name(session.id, artifact_name)
        if not artifact:
            return f"Artifact '{artifact_name}' not found in this session.", None, False

        artifact_id = artifact["id"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.artifact_service_url}/artifacts/{artifact_id}/unpin"
                )
                resp.raise_for_status()
            updated = resp.json()
        except Exception as e:
            return f"Error unpinning artifact '{artifact_name}': {e}", None, False

        expires_at = updated.get("expires_at")
        if expires_at:
            return (
                f"Artifact '{updated.get('name', artifact_name)}' is no longer pinned and will follow normal retention rules again. "
                f"Current expiration: {expires_at}."
            ), None, False

        return (
            f"Artifact '{updated.get('name', artifact_name)}' is no longer pinned and will follow normal retention rules again."
        ), None, False

    def _rows_to_csv(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""

        import csv
        import io

        fieldnames = list(rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()

    async def _execute_check_job_status(
        self, session: Session, tool_input: dict
    ) -> tuple[str, str | None, bool]:
        job_id = tool_input.get("job_id", "")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.execution_service_url}/jobs/{job_id}"
                )
            if resp.status_code == 404:
                return f"Job '{job_id}' not found.", None, False
            resp.raise_for_status()
        except Exception as e:
            return f"Error checking job status: {e}", None, False

        job = resp.json()
        status = job.get("status", "unknown")
        logs = job.get("logs", [])
        logs_str = "\n".join(f"  - {log}" for log in logs[-5:]) if logs else "  (no logs)"

        if status == "completed":
            result = job.get("result") or {}
            artifact_ids = result.get("artifact_ids", [])
            if artifact_ids:
                artifact_id = artifact_ids[0]
                summary = await self._get_artifact_summary(artifact_id)
                session.artifact_ids.append(artifact_id)
                self.sessions.save(session)
                return (
                    f"Job '{job_id}' has completed!\n\n{summary}\n\nLogs:\n{logs_str}"
                ), artifact_id, False
            return f"Job '{job_id}' completed but produced no artifacts.\n\nLogs:\n{logs_str}", None, False

        if status == "failed":
            error = job.get("error_message", "unknown error")
            return f"Job '{job_id}' failed: {error}\n\nLogs:\n{logs_str}", None, False

        if status == "running":
            return (
                f"Job '{job_id}' is still running. Check again shortly.\n\nLogs:\n{logs_str}"
            ), None, False

        return (
            f"Job '{job_id}' status: {status}.\n\nLogs:\n{logs_str}"
        ), None, False

    async def _get_artifact_summary(self, artifact_id: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.artifact_service_url}/artifacts/{artifact_id}"
            )
        if resp.status_code != 200:
            return f"Artifact {artifact_id} created."

        data = resp.json()
        name = data.get("name", "result")
        stats = data.get("statistics") or {}
        schema = data.get("schema_info") or {}
        columns = schema.get("columns", [])
        preview = data.get("preview") or {}
        preview_rows = preview.get("sample_rows") or []

        row_count = stats.get("row_count", "unknown")
        col_names = [c["name"] + f" ({c['logical_type']})" for c in columns]
        columns_str = ", ".join(col_names[:10])
        if len(col_names) > 10:
            columns_str += f", ... and {len(col_names) - 10} more"

        summary = (
            f"Query executed successfully. Artifact '{name}' created with {row_count} rows.\n"
            f"Columns: {columns_str}"
        )

        if preview_rows:
            preview_limit = min(len(preview_rows), 3)
            preview_str = self._rows_to_csv(preview_rows[:preview_limit]).strip()
            if preview_str:
                summary += (
                    f"\nPreview rows (first {preview_limit}):\n{preview_str}"
                )

        return summary

    # --- Context gathering ---

    async def _fetch_connections(self) -> list[ConnectionRecord]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.execution_service_url}/connections")
                resp.raise_for_status()
            return [ConnectionRecord(**c) for c in resp.json()]
        except Exception as e:
            logger.warning("Failed to fetch connections: %s", e)
            return []

    async def _fetch_session_artifacts(self, session_id: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.artifact_service_url}/artifacts",
                    params={"session_id": session_id},
                )
                resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to fetch artifacts: %s", e)
            return []

    async def _resolve_artifact_by_name(self, session_id: str, artifact_name: str) -> dict | None:
        all_artifacts = await self._fetch_session_artifacts(session_id)
        for artifact in all_artifacts:
            if artifact["name"] == artifact_name:
                return artifact
        return None

    async def _fetch_skills(
        self, connection_names: list[str], user_message: str
    ) -> list[SkillRecord]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.execution_service_url}/skills/resolve",
                    params={
                        "connection_names": ",".join(connection_names) if connection_names else "",
                        "user_message": user_message,
                    },
                )
                resp.raise_for_status()
            return [SkillRecord(**s) for s in resp.json()]
        except Exception as e:
            logger.warning("Failed to fetch skills: %s", e)
            return []

    async def _fetch_workflows(
        self,
        user_message: str,
        topic_context: ResolvedTopicContext | None = None,
    ) -> list[WorkflowRecord]:
        try:
            topic_profile_ids = ",".join(profile.id for profile in topic_context.profiles) if topic_context else ""
            active_workflow_ids = ",".join(topic_context.active_workflow_ids) if topic_context else ""
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.execution_service_url}/workflows/resolve",
                    params={
                        "user_message": user_message,
                        "topic_profile_ids": topic_profile_ids,
                        "active_workflow_ids": active_workflow_ids,
                    },
                )
                resp.raise_for_status()
            return [WorkflowRecord(**w) for w in resp.json()]
        except Exception as e:
            logger.warning("Failed to fetch workflows: %s", e)
            return []

    async def _fetch_topic_context(self, user_id: str) -> ResolvedTopicContext | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.execution_service_url}/topics/resolve",
                    params={"user_id": user_id},
                )
                resp.raise_for_status()
            ctx = ResolvedTopicContext(**resp.json())
            if ctx.profiles:
                logger.info(
                    "Topic context for user %s: %s",
                    user_id, [p.name for p in ctx.profiles],
                )
            return ctx if ctx.profiles else None
        except Exception as e:
            logger.warning("Failed to fetch topic context: %s", e)
            return None

    def _collect_active_policy_ids(
        self,
        workflows: list[WorkflowRecord] | None,
        topic_context: ResolvedTopicContext | None,
    ) -> list[str]:
        policy_ids: set[str] = set(topic_context.active_policy_ids if topic_context else [])
        for workflow in workflows or []:
            policy_ids.update(workflow.active_policy_ids)
        return sorted(policy_ids)

    def _collect_required_skill_ids(
        self,
        workflows: list[WorkflowRecord] | None,
    ) -> list[str]:
        skill_ids: set[str] = set()
        for workflow in workflows or []:
            skill_ids.update(workflow.required_skill_ids)
        return sorted(skill_ids)

    def _collect_preferred_tool_names(
        self,
        workflows: list[WorkflowRecord] | None,
    ) -> list[str]:
        preferred_tools: set[str] = set()
        for workflow in workflows or []:
            for step in workflow.steps:
                if step.preferred_tool:
                    normalized_tool = WORKFLOW_TOOL_TO_EXECUTION_TOOL.get(step.preferred_tool)
                    if normalized_tool:
                        preferred_tools.add(normalized_tool)
        return sorted(preferred_tools)

    def _collect_preferred_runtime_types(
        self,
        workflows: list[WorkflowRecord] | None,
    ) -> list[str]:
        preferred_runtimes: set[str] = set()
        for workflow in workflows or []:
            for step in workflow.steps:
                if step.preferred_runtime_type:
                    preferred_runtimes.add(step.preferred_runtime_type)
        return sorted(preferred_runtimes)

    def _build_workflow_trace(
        self,
        workflows: list[WorkflowRecord] | None,
        skills: list[SkillRecord] | None,
    ) -> list[dict[str, object]]:
        skill_name_by_id = {
            skill.id: skill.title or skill.name
            for skill in (skills or [])
        }
        trace: list[dict[str, object]] = []
        for workflow in workflows or []:
            preferred_tool_names = sorted(
                {
                    normalized_tool
                    for step in workflow.steps
                    if step.preferred_tool
                    for normalized_tool in [WORKFLOW_TOOL_TO_EXECUTION_TOOL.get(step.preferred_tool)]
                    if normalized_tool
                }
            )
            preferred_runtime_types = sorted(
                {
                    step.preferred_runtime_type
                    for step in workflow.steps
                    if step.preferred_runtime_type
                }
            )
            trace.append(
                {
                    "workflow_name": workflow.name,
                    "workflow_title": workflow.title,
                    "active_policy_ids": workflow.active_policy_ids,
                    "required_skill_ids": workflow.required_skill_ids,
                    "required_skill_names": [
                        skill_name_by_id.get(skill_id, skill_id)
                        for skill_id in workflow.required_skill_ids
                    ],
                    "preferred_tool_names": preferred_tool_names,
                    "preferred_runtime_types": preferred_runtime_types,
                }
            )
        return trace

    def _format_workflow_constraint_denial(
        self,
        tool_name: str,
        result: ExecutionResult,
        workflow_trace: list[dict[str, object]] | None,
    ) -> str | None:
        if not result.error_message or not workflow_trace:
            return None

        workflow_labels = [
            str(item.get("workflow_title") or item.get("workflow_name"))
            for item in workflow_trace
        ]
        workflow_prefix = (
            f"I couldn't continue because the active workflow ({', '.join(workflow_labels)}) "
            if len(workflow_labels) == 1
            else f"I couldn't continue because the active workflows ({', '.join(workflow_labels)}) "
        )

        if "preferred tool set" in result.error_message:
            preferred_tools = sorted(
                {
                    str(tool_name)
                    for item in workflow_trace
                    for tool_name in item.get("preferred_tool_names", [])
                }
            )
            suggested_tools = ", ".join(
                EXECUTION_TOOL_TO_AGENT_TOOL.get(tool_name, tool_name)
                for tool_name in preferred_tools
            )
            current_tool = EXECUTION_TOOL_TO_AGENT_TOOL.get(tool_name, tool_name)
            return (
                workflow_prefix
                + f"prefers {suggested_tools} for this turn, so I couldn't use {current_tool}."
            )

        if "preferred runtime" in result.error_message:
            preferred_runtimes = sorted(
                {
                    str(runtime_type)
                    for item in workflow_trace
                    for runtime_type in item.get("preferred_runtime_types", [])
                }
            )
            runtime_list = ", ".join(preferred_runtimes)
            return workflow_prefix + f"requires the {runtime_list} runtime for this turn."

        if "requires active skills" in result.error_message:
            required_skill_names = sorted(
                {
                    str(skill_name)
                    for item in workflow_trace
                    for skill_name in item.get("required_skill_names", [])
                }
            )
            return (
                workflow_prefix
                + "requires these skills to be active first: "
                + ", ".join(required_skill_names)
                + "."
            )

        return None

    # --- Prompt building ---

    def _build_system_prompt(
        self,
        connections: list[ConnectionRecord],
        artifacts: list[dict],
        tools: list[ToolDefinition],
        skills: list[SkillRecord] | None = None,
        workflows: list[WorkflowRecord] | None = None,
        topic_context: ResolvedTopicContext | None = None,
    ) -> str:
        parts = [
            "You are an analytics agent. You help users retrieve and analyze data from connected sources.",
            "You write SQL queries to fetch data, and results are saved as reusable table artifacts in the session.",
            "You can also transform data using Python code that operates on previously created artifacts.",
            "You can inspect existing artifacts to see sample rows and column details.",
            "",
            "## Available connections",
        ]

        if connections:
            for c in connections:
                parts.append(f"- **{c.name}** (type: {c.type}): {c.display_name or c.name}")
        else:
            parts.append("No connections available.")

        parts.append("")
        parts.append("## Available tools for this turn")
        for tool in tools:
            parts.append(f"- **{tool.name}**: {tool.description}")

        parts.append("")
        parts.append("## Session artifacts")

        if artifacts:
            for a in artifacts:
                schema = a.get("schema_info") or {}
                cols = schema.get("columns", [])
                col_summary = ", ".join(c["name"] for c in cols[:8])
                stats = a.get("statistics") or {}
                rows = stats.get("row_count", "?")
                status_bits = []
                if a.get("is_pinned"):
                    status_bits.append("pinned")
                expires_at = a.get("expires_at")
                if expires_at:
                    status_bits.append(f"expires {expires_at}")
                status_suffix = f" [{'; '.join(status_bits)}]" if status_bits else ""
                parts.append(f"- **{a['name']}** ({rows} rows): [{col_summary}]{status_suffix}")
        else:
            parts.append("No artifacts in this session yet.")

        parts.extend([
            "",
            "## Instructions",
            "- When the user asks for data, determine the right connection and write a SQL query.",
            "- Use the query_sql_source tool to execute queries.",
            "- Use the transform_with_python tool to filter, aggregate, or transform existing artifacts.",
            "- When using transform_with_python, input artifacts are available as pandas DataFrames with the variable names matching the artifact aliases.",
            "- Your code must assign the final result to a variable called `result` (a DataFrame).",
            "- Use the inspect_artifact tool to look at sample rows or column details of an existing artifact.",
            "- Use the pin_artifact tool when the user wants to keep an artifact available for later.",
            "- Use the unpin_artifact tool when the user wants to remove that cleanup protection.",
            "- Give artifacts clear, descriptive snake_case names.",
            "- After getting results, summarize what was found.",
            "- You can reference prior artifacts by name when the user asks follow-up questions.",
            "- When the user wants to refine or filter a prior result, prefer transform_with_python over re-querying the source.",
            "- Be efficient: combine multiple calculations into a single query when possible rather than running separate queries for each metric.",
            "- Only use inspect_artifact when you genuinely need to see data values. You already get column names and row counts from query results.",
            "- Large SQL queries and large Python transforms may be routed to background processing by the execution service.",
            "- If a tool call is deferred (runs as a background job), tell the user and use check_job_status to check on it later.",
            "- Do not claim a tool is unavailable unless it is absent from the 'Available tools for this turn' list above.",
        ])

        # Active skills
        if skills:
            parts.append("")
            parts.append("## Active skills")
            for skill in skills:
                parts.append(f"### {skill.title or skill.name} ({skill.category.value})")
                parts.append(skill.instructions.summary)
                if skill.instructions.recommended_steps:
                    parts.append("Recommended steps:")
                    for step in skill.instructions.recommended_steps:
                        parts.append(f"  - {step}")
                if skill.instructions.dos:
                    parts.append("Do:")
                    for do in skill.instructions.dos:
                        parts.append(f"  - {do}")
                if skill.instructions.donts:
                    parts.append("Don't:")
                    for dont in skill.instructions.donts:
                        parts.append(f"  - {dont}")
                if skill.instructions.output_expectations:
                    parts.append("Expected output:")
                    for exp in skill.instructions.output_expectations:
                        parts.append(f"  - {exp}")
                parts.append("")

        if workflows:
            parts.append("")
            parts.append("## Active workflows")
            for workflow in workflows:
                parts.append(f"### {workflow.title or workflow.name}")
                if workflow.description:
                    parts.append(workflow.description)
                if workflow.output_expectations:
                    parts.append("Workflow outputs:")
                    for output in workflow.output_expectations:
                        parts.append(f"  - {output}")
                if workflow.steps:
                    parts.append("Suggested workflow steps:")
                    for step in sorted(workflow.steps, key=lambda item: item.order):
                        tool_hint = f" [{step.preferred_tool}]" if step.preferred_tool else ""
                        parts.append(f"  - Step {step.order}: {step.title}{tool_hint} — {step.description}")
                parts.append("")

        # Topic profile context
        if topic_context and topic_context.profiles:
            parts.append("")
            parts.append("## Active topic profiles")
            for profile in topic_context.profiles:
                parts.append(f"- **{profile.display_name or profile.name}**: {profile.description or ''}")
            if topic_context.allowed_tool_names:
                parts.append(f"\nYou may only use these tools: {', '.join(topic_context.allowed_tool_names)}")
            if topic_context.allowed_connection_names:
                parts.append(f"You may only access these connections: {', '.join(topic_context.allowed_connection_names)}")
            parts.append("")

        return "\n".join(parts)

    def _build_llm_messages(self, session: Session) -> list[Message]:
        messages: list[Message] = []
        for msg in session.messages:
            messages.append(Message(role=msg["role"], content=msg["content"]))
        return messages
