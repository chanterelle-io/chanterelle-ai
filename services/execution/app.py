import logging

from fastapi import FastAPI

from shared.contracts.connection import ConnectionRecord
from shared.contracts.execution import ExecutionRequest, ExecutionResult
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
