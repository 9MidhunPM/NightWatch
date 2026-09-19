from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status

from nightwatch.config import Settings
from nightwatch.events.bus import EventBus
from nightwatch.events.models import RealtimeEvent
from nightwatch.security.access import RealtimeTicketRegistry

router = APIRouter(tags=["events"])


@router.post("/realtime-ticket")
async def create_realtime_ticket(request: Request) -> dict[str, str]:
    settings = cast(Settings, request.app.state.settings)
    secret = settings.frontend_token.get_secret_value() if settings.frontend_token else ""
    registry = cast(RealtimeTicketRegistry, request.app.state.realtime_tickets)
    return {"ticket": registry.issue(secret, settings.realtime_ticket_ttl_seconds)}


@router.websocket("/events")
async def event_stream(websocket: WebSocket) -> None:
    settings = cast(Settings, websocket.app.state.settings)
    origin = websocket.headers.get("origin")
    token = next(
        (
            item.strip()
            for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if item.strip().startswith("nightwatch-ticket.")
        ),
        None,
    )
    ticket = token.removeprefix("nightwatch-ticket.") if token else None
    secret = settings.frontend_token.get_secret_value() if settings.frontend_token else ""
    registry = cast(RealtimeTicketRegistry, websocket.app.state.realtime_tickets)
    if origin not in settings.websocket_origins or not registry.consume(ticket, secret):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept(subprotocol=token)
    bus = cast(EventBus, websocket.app.state.event_bus)
    try:
        async with bus.subscribe() as queue:
            await bus.publish(RealtimeEvent(payload={"source": "connection"}))
            while True:
                event = await queue.get()
                if event is None:
                    await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
                    return
                await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
