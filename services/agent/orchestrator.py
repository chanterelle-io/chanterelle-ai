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
from shared.contracts.connection import ConnectionRecord
from shared.contracts.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionTarget,
    ExpectedOutput,
    ToolInvocation,
)
from shared.settings import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


class Orchestrator:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.sessions = SessionStore()

    async def handle_message(self, session_id: str, user_message: str) -> dict:
        session = self.sessions.get_or_create(session_id)

        # Gather context for the system prompt
        connections = await self._fetch_connections()
        artifacts = await self._fetch_session_artifacts(session_id)

        system_prompt = self._build_system_prompt(connections, artifacts)
        tools = [SQL_QUERY_TOOL]

        # Add user message
        session.messages.append({"role": "user", "content": user_message})

        # Run the tool-use loop
        messages = self._build_llm_messages(session)
        new_artifact_ids: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.llm.chat(system=system_prompt, messages=messages, tools=tools)

            if response.stop_reason == "end_turn" or not response.tool_calls:
                # Done — record assistant response
                session.messages.append({"role": "assistant", "content": response.text or ""})
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
            for tc in response.tool_calls:
                result_text, artifact_id = await self._execute_tool(session, tc)
                tool_results.append(ToolResult(tool_call_id=tc.id, content=result_text))
                if artifact_id:
                    new_artifact_ids.append(artifact_id)
                    session.artifact_ids.append(artifact_id)

            # Add tool results as a user message
            messages.append(Message(role="user", tool_results=tool_results))

            # Also record in session history for persistence
            session.messages.append({
                "role": "assistant",
                "content": f"[Used tool: {response.tool_calls[0].name}]",
            })
        else:
            session.messages.append({
                "role": "assistant",
                "content": "I reached the maximum number of tool steps. Here is what I have so far.",
            })

        return {
            "session_id": session_id,
            "message": session.messages[-1]["content"],
            "artifact_ids": new_artifact_ids,
        }

    # --- Tool execution ---

    async def _execute_tool(
        self, session: Session, tool_call: ToolCall
    ) -> tuple[str, str | None]:
        if tool_call.name == "query_sql_source":
            return await self._execute_sql_query(session, tool_call.input)
        return f"Unknown tool: {tool_call.name}", None

    async def _execute_sql_query(
        self, session: Session, tool_input: dict
    ) -> tuple[str, str | None]:
        connection_name = tool_input.get("connection_name", "")
        query = tool_input.get("query", "")
        artifact_name = tool_input.get("artifact_name", "query_result")

        exec_request = ExecutionRequest(
            session_id=session.id,
            tool=ToolInvocation(
                tool_name="query_sql",
                operation="query",
                payload={"query": query},
            ),
            target=ExecutionTarget(connection_name=connection_name),
            expected_outputs=[ExpectedOutput(name=artifact_name, type="table")],
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.execution_service_url}/execute",
                json=exec_request.model_dump(),
            )

        if resp.status_code != 200:
            error_detail = resp.json().get("detail", resp.text)
            return f"Error executing query: {error_detail}", None

        result = ExecutionResult(**resp.json())
        if result.status == "error":
            return f"Query failed: {result.error_message}", None

        # Fetch artifact metadata for the summary
        artifact_id = result.artifact_ids[0] if result.artifact_ids else None
        if artifact_id:
            summary = await self._get_artifact_summary(artifact_id)
            return summary, artifact_id

        return "Query executed but no artifact was produced.", None

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

        row_count = stats.get("row_count", "unknown")
        col_names = [c["name"] + f" ({c['logical_type']})" for c in columns]
        columns_str = ", ".join(col_names[:10])
        if len(col_names) > 10:
            columns_str += f", ... and {len(col_names) - 10} more"

        return (
            f"Query executed successfully. Artifact '{name}' created with {row_count} rows.\n"
            f"Columns: {columns_str}"
        )

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

    # --- Prompt building ---

    def _build_system_prompt(
        self, connections: list[ConnectionRecord], artifacts: list[dict]
    ) -> str:
        parts = [
            "You are an analytics agent. You help users retrieve and analyze data from connected sources.",
            "You write SQL queries to fetch data, and results are saved as reusable table artifacts in the session.",
            "",
            "## Available connections",
        ]

        if connections:
            for c in connections:
                parts.append(f"- **{c.name}** (type: {c.type}): {c.display_name or c.name}")
        else:
            parts.append("No connections available.")

        parts.append("")
        parts.append("## Session artifacts")

        if artifacts:
            for a in artifacts:
                schema = a.get("schema_info") or {}
                cols = schema.get("columns", [])
                col_summary = ", ".join(c["name"] for c in cols[:8])
                stats = a.get("statistics") or {}
                rows = stats.get("row_count", "?")
                parts.append(f"- **{a['name']}** ({rows} rows): [{col_summary}]")
        else:
            parts.append("No artifacts in this session yet.")

        parts.extend([
            "",
            "## Instructions",
            "- When the user asks for data, determine the right connection and write a SQL query.",
            "- Use the query_sql_source tool to execute queries.",
            "- Give artifacts clear, descriptive snake_case names.",
            "- After getting results, summarize what was found.",
            "- You can reference prior artifacts by name when the user asks follow-up questions.",
        ])

        return "\n".join(parts)

    def _build_llm_messages(self, session: Session) -> list[Message]:
        messages: list[Message] = []
        for msg in session.messages:
            messages.append(Message(role=msg["role"], content=msg["content"]))
        return messages
