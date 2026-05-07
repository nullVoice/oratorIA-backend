"""Connection registry for live sessions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable

from fastapi import WebSocket


class ConnectionManager:
    """In-process WebSocket registry. Replace with Redis pub/sub for multi-worker setups."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(session_id)
            if conns and websocket in conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(session_id, None)

    def peers(self, session_id: uuid.UUID) -> Iterable[WebSocket]:
        return tuple(self._connections.get(session_id, set()))


manager = ConnectionManager()
