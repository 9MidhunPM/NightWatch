from typing import cast

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status

from nightwatch.config import Settings
from nightwatch.events.models import RealtimeEvent
from nightwatch.security.access import RealtimeTicketRegistry

router = APIRouter(tags=["events"])


@router.post("/realtime-ticket")
async def create_realtime_ticket(request: Request) -> dict[str, str]:
    settings = cast(Settings, request.app.state.settings)
    secret = settings.frontend_token.get_secret_value() if settings.frontend_token else ""
    tickets = cast(RealtimeTicketRegistry, request.app.state.realtime_tickets)
    return {"ticket": tickets.issue(secret, settings.realtime_ticket_ttl_seconds)}


def is_origin_allowed(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
    return origin is not None and origin in allowed_origins


@router.websocket("/events")
async def event_stream(websocket: WebSocket) -> None:
    allowed_origins = websocket.app.state.settings.websocket_origins
    origin = websocket.headers.get("origin")
    configured_token = websocket.app.state.settings.frontend_token
    secret = configured_token.get_secret_value() if configured_token else ""
    tickets = cast(RealtimeTicketRegistry, websocket.app.state.realtime_tickets)
    protocol = next(
        (item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",") if item.strip().startswith("nightwatch-ticket.")),
        None,
    )
    ticket = protocol.removeprefix("nightwatch-ticket.") if protocol else None
    if not is_origin_allowed(origin, allowed_origins) or not tickets.consume(
        ticket, secret
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept(subprotocol=protocol)
    bus = websocket.app.state.event_bus
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
