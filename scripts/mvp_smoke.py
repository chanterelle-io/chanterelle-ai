from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


class SmokeFailure(RuntimeError):
    pass


@dataclass
class ServiceUrls:
    agent: str = "http://localhost:8000"
    execution: str = "http://localhost:8001"
    artifact: str = "http://localhost:8002"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def json_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_status: int = 200,
    **kwargs,
) -> dict | list:
    response = client.request(method, url, **kwargs)
    if response.status_code != expected_status:
        detail = response.text.strip()
        raise SmokeFailure(
            f"{method} {url} returned {response.status_code} instead of {expected_status}: {detail}"
        )
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{method} {url} did not return JSON: {exc}") from exc


def poll_job_completion(
    client: httpx.Client,
    execution_url: str,
    job_id: str,
    timeout_seconds: float = 20.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_job: dict | None = None
    while time.monotonic() < deadline:
        last_job = json_request(client, "GET", f"{execution_url}/jobs/{job_id}")
        status = last_job.get("status")
        if status in {"completed", "failed"}:
            return last_job
        time.sleep(0.5)
    raise SmokeFailure(f"Deferred job {job_id} did not finish within {timeout_seconds:.1f}s: {last_job}")


def check_service_connectivity(client: httpx.Client, urls: ServiceUrls) -> None:
    agent_health = json_request(client, "GET", f"{urls.agent}/health")
    expect(agent_health.get("status") == "ok", "Agent health check did not return ok")

    connections = json_request(client, "GET", f"{urls.execution}/connections")
    expect(any(conn.get("name") == "sample_db" for conn in connections), "sample_db connection is not available")

    artifacts = json_request(
        client,
        "GET",
        f"{urls.artifact}/artifacts",
        params={"session_id": "mvp-smoke-empty-check"},
    )
    expect(isinstance(artifacts, list), "Artifact list endpoint did not return a list")


def check_chat_round_trip(client: httpx.Client, urls: ServiceUrls, suffix: str) -> tuple[str, str]:
    session_id = f"mvp-chat-{suffix}"
    response = json_request(
        client,
        "POST",
        f"{urls.agent}/chat",
        json={
            "session_id": session_id,
            "user_id": "finance-user",
            "message": "Use SQL on sample_db to return the first 5 active customers by id with columns id, name, and status.",
        },
    )
    expect(response.get("session_id") == session_id, "Chat response returned an unexpected session id")
    expect(bool((response.get("message") or "").strip()), "Chat response message was empty")

    artifact_ids = response.get("artifact_ids") or []
    expect(artifact_ids, "Chat response did not create an artifact for the bounded MVP query")

    session = json_request(client, "GET", f"{urls.agent}/sessions/{session_id}")
    expect(session.get("message_count", 0) >= 2, "Agent session did not persist both user and assistant turns")
    expect(artifact_ids[0] in (session.get("artifact_ids") or []), "Agent session did not track the chat artifact")
    return session_id, artifact_ids[0]


def check_sql_execution(client: httpx.Client, urls: ServiceUrls, suffix: str) -> tuple[str, str]:
    session_id = f"mvp-exec-{suffix}"
    result = json_request(
        client,
        "POST",
        f"{urls.execution}/execute",
        json={
            "session_id": session_id,
            "user_id": "analyst-user",
            "tool": {
                "tool_name": "query_sql",
                "operation": "query",
                "payload": {
                    "query": "SELECT id, name, status FROM customers ORDER BY id LIMIT 5",
                },
            },
            "target": {"connection_name": "sample_db"},
            "expected_outputs": [{"name": "mvp_smoke_customers"}],
        },
    )
    expect(result.get("status") == "success", f"Direct SQL execution failed: {result}")
    artifact_ids = result.get("artifact_ids") or []
    expect(len(artifact_ids) == 1, f"Direct SQL execution returned unexpected artifacts: {result}")

    artifact = json_request(client, "GET", f"{urls.artifact}/artifacts/{artifact_ids[0]}")
    statistics = artifact.get("statistics") or {}
    expect(statistics.get("row_count") == 5, f"SQL artifact row_count was not 5: {artifact}")
    return session_id, artifact_ids[0]


def check_python_transform(
    client: httpx.Client,
    urls: ServiceUrls,
    session_id: str,
    source_artifact_id: str,
) -> str:
    result = json_request(
        client,
        "POST",
        f"{urls.execution}/execute",
        json={
            "session_id": session_id,
            "user_id": "analyst-user",
            "tool": {
                "tool_name": "python_transform",
                "operation": "transform",
                "payload": {
                    "code": 'result = customers[["id", "name"]].copy()',
                },
            },
            "input_artifacts": [{"artifact_id": source_artifact_id, "alias": "customers"}],
            "expected_outputs": [{"name": "mvp_smoke_customers_names"}],
        },
    )
    expect(result.get("status") == "success", f"Python transform failed: {result}")
    artifact_ids = result.get("artifact_ids") or []
    expect(len(artifact_ids) == 1, f"Python transform returned unexpected artifacts: {result}")

    artifact = json_request(client, "GET", f"{urls.artifact}/artifacts/{artifact_ids[0]}")
    columns = ((artifact.get("schema_info") or {}).get("columns") or [])
    column_names = [column.get("name") for column in columns]
    expect(column_names == ["id", "name"], f"Python transform returned unexpected columns: {column_names}")
    return artifact_ids[0]


def check_topic_restriction(client: httpx.Client, urls: ServiceUrls, suffix: str) -> None:
    result = json_request(
        client,
        "POST",
        f"{urls.execution}/execute",
        json={
            "session_id": f"mvp-finance-policy-{suffix}",
            "user_id": "finance-user",
            "tool": {
                "tool_name": "python_transform",
                "operation": "transform",
                "payload": {"code": 'result = pd.DataFrame({"x": [1]})'},
            },
        },
    )
    expect(result.get("status") == "denied", f"Finance Python restriction did not deny execution: {result}")
    error_message = result.get("error_message") or ""
    expect("denied" in error_message.lower(), f"Denied execution returned an unexpected message: {result}")


def check_deferred_job(client: httpx.Client, urls: ServiceUrls, suffix: str) -> str:
    result = json_request(
        client,
        "POST",
        f"{urls.execution}/execute",
        json={
            "session_id": f"mvp-deferred-{suffix}",
            "user_id": "analyst-user",
            "tool": {
                "tool_name": "query_sql",
                "operation": "query",
                "payload": {"query": "SELECT * FROM customers"},
            },
            "target": {"connection_name": "sample_db"},
            "expected_outputs": [{"name": "mvp_smoke_customers_deferred"}],
        },
    )
    expect(result.get("status") == "deferred", f"Large SQL query was not deferred: {result}")
    job_id = result.get("job_id")
    expect(bool(job_id), f"Deferred execution did not return a job_id: {result}")

    job = poll_job_completion(client, urls.execution, job_id)
    expect(job.get("status") == "completed", f"Deferred job did not complete successfully: {job}")
    job_result = job.get("result") or {}
    artifact_ids = job_result.get("artifact_ids") or []
    expect(artifact_ids, f"Deferred job completed without output artifacts: {job}")
    return artifact_ids[0]


def check_retention_controls(client: httpx.Client, urls: ServiceUrls, session_id: str, artifact_id: str) -> None:
    quota = json_request(
        client,
        "GET",
        f"{urls.artifact}/artifacts/quota",
        params={"session_id": session_id},
    )
    expect((quota.get("used_bytes") or 0) > 0, f"Quota summary did not reflect stored artifacts: {quota}")

    pinned = json_request(client, "POST", f"{urls.artifact}/artifacts/{artifact_id}/pin")
    expect(pinned.get("is_pinned") is True, f"Pin endpoint did not pin artifact: {pinned}")

    unpinned = json_request(client, "POST", f"{urls.artifact}/artifacts/{artifact_id}/unpin")
    expect(unpinned.get("is_pinned") is False, f"Unpin endpoint did not clear pin state: {unpinned}")


def run_smoke(urls: ServiceUrls) -> None:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    timeout = httpx.Timeout(120.0, connect=5.0)
    with httpx.Client(timeout=timeout) as client:
        print("[1/6] Checking service connectivity...")
        check_service_connectivity(client, urls)

        print("[2/6] Checking agent chat round-trip...")
        _, _ = check_chat_round_trip(client, urls, suffix)

        print("[3/6] Checking direct SQL execution and artifact registration...")
        exec_session_id, sql_artifact_id = check_sql_execution(client, urls, suffix)

        print("[4/6] Checking Python transform and topic policy restriction...")
        check_python_transform(client, urls, exec_session_id, sql_artifact_id)
        check_topic_restriction(client, urls, suffix)

        print("[5/6] Checking deferred execution and job completion...")
        check_deferred_job(client, urls, suffix)

        print("[6/6] Checking retention pin/unpin and quota visibility...")
        check_retention_controls(client, urls, exec_session_id, sql_artifact_id)

    print("MVP smoke test passed.")


def parse_args() -> ServiceUrls:
    parser = argparse.ArgumentParser(description="Run the local MVP smoke test against live services.")
    parser.add_argument("--agent-url", default="http://localhost:8000")
    parser.add_argument("--execution-url", default="http://localhost:8001")
    parser.add_argument("--artifact-url", default="http://localhost:8002")
    args = parser.parse_args()
    return ServiceUrls(agent=args.agent_url, execution=args.execution_url, artifact=args.artifact_url)


if __name__ == "__main__":
    try:
        run_smoke(parse_args())
    except SmokeFailure as exc:
        print(f"MVP smoke test failed: {exc}", file=sys.stderr)
        sys.exit(1)