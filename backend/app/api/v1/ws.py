"""
WebSocket endpoint for real-time notifications.

WHY THE TOKEN IS A QUERY PARAMETER, NOT AN AUTHORIZATION HEADER:
Browser WebSocket APIs (`new WebSocket(url)`) have no way to attach
custom headers to the handshake request — unlike fetch/axios, there's no
headers option. The standard workaround, used across the industry, is to
pass the access token as a query parameter instead:
`wss://.../ws/notifications?token=...`. This is part of why the access
token is deliberately SHORT-LIVED (15 minutes — see core/security.py):
query parameters are more likely to end up in server access logs or
browser history than an Authorization header, so anything long-lived
there would be a bigger exposure than it is elsewhere.
"""
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.core.ws_manager import connection_manager
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/notifications")
async def notifications_websocket(
    websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)
):
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4401)
            return
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        await websocket.close(code=4401)
        return

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        await websocket.close(code=4401)
        return

    await connection_manager.connect(user_id, websocket)
    try:
        while True:
            # This socket is push-only from the server — we don't expect
            # the client to send anything meaningful. We still await
            # receive() because that's how a closed connection surfaces
            # (as WebSocketDisconnect), which is what we need to clean up
            # the registry entry.
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(user_id, websocket)
