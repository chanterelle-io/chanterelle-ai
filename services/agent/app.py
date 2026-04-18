import logging

from fastapi import FastAPI
from pydantic import BaseModel

from services.agent.llm.claude import ClaudeProvider
from services.agent.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Service", version="0.1.0")

llm = ClaudeProvider()
orchestrator = Orchestrator(llm=llm)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    artifact_ids: list[str] = []


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    logger.info("Chat request for session %s (user=%s)", req.session_id, req.user_id)
    result = await orchestrator.handle_message(
        session_id=req.session_id,
        user_message=req.message,
        user_id=req.user_id,
    )
    return ChatResponse(**result)


@app.get("/health")
def health():
    return {"status": "ok"}
