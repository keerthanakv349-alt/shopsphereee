"""
WebSocket connection registry.

WHY IN-MEMORY, NOT REDIS PUB/SUB:
This maps user_id -> a list of currently-open WebSocket connections,
held in this process's memory. It works correctly as long as the API
runs as a SINGLE process/instance. The moment you run more than one
backend instance behind a load balancer (which any real production
deployment would, for redundancy and throughput), a notification
generated on instance A can't reach a user whose WebSocket happens to be
connected to instance B — this in-memory map is invisible across
processes. The real fix is a pub/sub layer (Redis Pub/Sub, or a message
broker) that every instance subscribes to, so any instance can broadcast
to a user regardless of which instance they're connected to. That's a
Phase 7 (hardening/deployment) concern — this simple version is correct
and fully functional for local development and single-instance
deployments, which is exactly the stage this build is at.
"""
import uuid

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, list[WebSocket]] = {}

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._connections.get(user_id, [])):
            try:
                await websocket.send_json(payload)
            except Exception:
                # A dead/closed socket shouldn't take down the request that
                # triggered the notification — drop it and move on; the
                # persisted Notification row (see models/notification.py)
                # is what the user sees next time they load the page anyway.
                self.disconnect(user_id, websocket)


# Module-level singleton — every route imports this same instance, since
# the whole point is one shared registry per process.
connection_manager = ConnectionManager()
