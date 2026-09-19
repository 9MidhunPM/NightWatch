import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, StreamingResponse

from nightwatch.models.operations_api import (
    AgentConversationDetail,
    AgentConversationSummary,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentStatusResponse,
    OperationsReport,
    ResourceSnapshot,
)
from nightwatch.services.beszel_service import BeszelService
from nightwatch.services.conversation_service import ConversationService
from nightwatch.services.operations_service import OperationsService

router = APIRouter(tags=["operations"])
logger = logging.getLogger("nightwatch.operations_api")


def service(request: Request) -> OperationsService:
    return cast(OperationsService, request.app.state.operations_service)


def conversations(request: Request) -> ConversationService:
    return cast(ConversationService, request.app.state.conversation_service)


@router.get("/resources", response_model=ResourceSnapshot)
async def resources(request: Request) -> ResourceSnapshot:
    return await service(request).resources()


@router.post("/agent/messages", response_model=AgentMessageResponse)
async def agent_message(request: Request, payload: AgentMessageRequest) -> AgentMessageResponse:
    reply, _conversation_id = await conversations(request).respond(payload.conversation_id, payload.message)
    return reply


@router.get("/agent/conversations", response_model=list[AgentConversationSummary])
async def list_conversations(request: Request) -> list[AgentConversationSummary]:
    return await conversations(request).list()


@router.post("/agent/conversations", response_model=AgentConversationDetail)
async def create_conversation(request: Request) -> AgentConversationDetail:
    return await conversations(request).create()


@router.get("/agent/conversations/{conversation_id}", response_model=AgentConversationDetail)
async def get_conversation(request: Request, conversation_id: str) -> AgentConversationDetail:
    conversation = await conversations(request).get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation was not found.")
    return conversation


@router.post("/agent/conversations/{conversation_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(request: Request, conversation_id: str) -> None:
    if not await conversations(request).archive(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation was not found.")


@router.post("/agent/stream")
async def agent_stream(request: Request, payload: AgentMessageRequest) -> StreamingResponse:
    """Stream observable progress, never model reasoning, before the final answer."""
    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def publish(event: dict[str, object]) -> None:
            await queue.put(event)

        task = asyncio.create_task(conversations(request).respond(payload.conversation_id, payload.message, publish), name="nightwatch-agent-turn")
        while not task.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.25)
            except TimeoutError:
                continue
            yield f"event: activity\ndata: {json.dumps(event, default=str)}\n\n"
        while not queue.empty():
            yield f"event: activity\ndata: {json.dumps(queue.get_nowait(), default=str)}\n\n"
        try:
            reply, conversation_id = await task
        except Exception:
            logger.exception("Agent stream failed")
            yield 'event: answer\ndata: {"answer":"Nightwatch could not complete that observation safely. Please try again.","findings":[],"citations":[],"suggested_questions":[],"activity":[]}\n\n'
            return
        yield f"event: answer\ndata: {reply.model_dump_json()}\n\n"
        yield f"event: conversation\ndata: {json.dumps({'id': conversation_id})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/agent/status", response_model=AgentStatusResponse)
async def agent_status(request: Request) -> AgentStatusResponse:
    return service(request).agent_status()


@router.get("/observability/beszel")
async def beszel_status(request: Request) -> dict[str, object]:
    connection = await cast(BeszelService, request.app.state.beszel_service).connection()
    return {"configured": connection.configured, "available": connection.available, "message": connection.message, "system_id": connection.system_id}


@router.get("/reports/current", response_model=OperationsReport)
async def current_report(request: Request) -> OperationsReport:
    return await service(request).report()


@router.get("/reports/current.csv", response_class=PlainTextResponse)
async def current_report_csv(request: Request) -> str:
    report = await service(request).report()
    rows = ["container_id,cpu_percent,memory_used_bytes,memory_limit_bytes,network_rx_bytes,network_tx_bytes,observed_at"]
    rows.extend(",".join(str(value if value is not None else "") for value in (item.container_id, item.cpu_percent, item.memory_used_bytes, item.memory_limit_bytes, item.network_rx_bytes, item.network_tx_bytes, item.observed_at.isoformat())) for item in report.resource_usage)
    return "\n".join(rows) + "\n"
