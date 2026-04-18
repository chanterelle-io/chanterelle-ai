import logging

from fastapi import FastAPI

from shared.contracts.connection import ConnectionRecord
from shared.contracts.execution import ExecutionRequest, ExecutionResult
from shared.contracts.runtime import RuntimeRecord
from shared.contracts.skill import SkillRecord
from shared.contracts.policy import PolicyRecord, PolicyEvaluation
from shared.contracts.topic import TopicProfile, UserTopicAssignment, ResolvedTopicContext
from services.execution.manager import ExecutionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Execution Service", version="0.1.0")

manager = ExecutionManager()


@app.post("/execute", response_model=ExecutionResult)
async def execute(req: ExecutionRequest) -> ExecutionResult:
    logger.info("Execution request %s: tool=%s", req.id, req.tool.tool_name)
    return await manager.execute(req)


@app.get("/connections", response_model=list[ConnectionRecord])
def list_connections() -> list[ConnectionRecord]:
    return manager.list_connections()


@app.get("/runtimes", response_model=list[RuntimeRecord])
def list_runtimes() -> list[RuntimeRecord]:
    return manager.list_runtimes()


@app.get("/skills", response_model=list[SkillRecord])
def list_skills() -> list[SkillRecord]:
    return manager.list_skills()


@app.get("/skills/resolve", response_model=list[SkillRecord])
def resolve_skills(
    connection_names: str | None = None,
    user_message: str | None = None,
) -> list[SkillRecord]:
    conn_names = connection_names.split(",") if connection_names else None
    return manager.get_skills_for_context(
        connection_names=conn_names,
        user_message=user_message,
    )


@app.get("/policies", response_model=list[PolicyRecord])
def list_policies() -> list[PolicyRecord]:
    return manager.list_policies()


@app.get("/policies/evaluate", response_model=PolicyEvaluation)
def evaluate_policies(
    tool_name: str | None = None,
    connection_type: str | None = None,
    topic_profile_ids: str | None = None,
) -> PolicyEvaluation:
    profile_ids = topic_profile_ids.split(",") if topic_profile_ids else None
    return manager.evaluate_policies(
        tool_name=tool_name,
        connection_type=connection_type,
        topic_profile_ids=profile_ids,
    )


@app.get("/topics", response_model=list[TopicProfile])
def list_topic_profiles() -> list[TopicProfile]:
    return manager.list_topic_profiles()


@app.get("/topics/resolve", response_model=ResolvedTopicContext)
def resolve_topic_context(user_id: str) -> ResolvedTopicContext:
    return manager.resolve_topic_context(user_id)
