"""WebSocket endpoint for live coaching sessions.

Receives audio chunks from the client, runs them through the orchestrator,
and streams back evaluator feedback in real time.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from oratoria.api.ws.connection import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/sessions/{session_id}")
async def live_session_ws(websocket: WebSocket, session_id: uuid.UUID) -> None:
    await manager.connect(session_id, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            audio_chunk = message.get("bytes")
            if audio_chunk is None:
                # Treat text frames as control messages (start/stop/finish).
                text = message.get("text") or ""
                await websocket.send_json({"type": "ack", "control": text})
                continue

            # TODO: stream chunk into orchestrator (Whisper streaming + paraverbal),
            # then push partial feedback back to the client.
            await websocket.send_json(
                {
                    "type": "partial",
                    "session_id": str(session_id),
                    "bytes_received": len(audio_chunk),
                }
            )
    except WebSocketDisconnect:
        logger.info("Live session %s disconnected", session_id)
    except Exception:
        logger.exception("Error in live session %s", session_id)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        await manager.disconnect(session_id, websocket)
