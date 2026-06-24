"""OpenAI-compatible LLM endpoint for Tavus persona brain (Audiencia Digital)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from oratoria.ai.agents.persona import PersonaAgent
from oratoria.ai.prompts.persona_prompt import build_persona_system_prompt
from oratoria.config import settings
from oratoria.database import get_db
from oratoria.models import Session as SessionModel

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_SYSTEM_PROMPT = (
    "Eres una audiencia atenta escuchando una presentación. "
    "Responde de forma breve y natural, como lo haría una persona real."
)


class OpenAIMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "oratoria-persona"
    messages: list[OpenAIMessage]
    stream: bool = True


def _verify_token(token: str | None) -> None:
    secret_setting = settings.persona_llm_secret
    if secret_setting is None:
        return  # dev mode — no check
    secret = secret_setting.get_secret_value()
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-Oratoria-Persona-Token."
        )


async def _resolve_system_prompt(
    session_id: uuid.UUID | None,
    messages: list[OpenAIMessage],
    db: DBSession,
) -> str:
    if session_id is not None:
        sess = await db.get(SessionModel, session_id)
        if sess is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Session {session_id} not found.")
        ctx = sess.context or {}
        return build_persona_system_prompt(
            segment=ctx.get("segment"),
            presentation_type=ctx.get("presentation_type"),
            audience=ctx.get("audience"),
            objective=ctx.get("objective"),
            formality=ctx.get("formality"),
            duration_target=ctx.get("duration_target"),
            interactive=bool(ctx.get("avatar_interactive", False)),
            user_full_name=ctx.get("user_full_name"),
        )
    # Fallback: use first system message in incoming messages
    for msg in messages:
        if msg.role == "system":
            return msg.content
    return _DEFAULT_SYSTEM_PROMPT


def _make_chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_oratoria_persona_token: str | None = Header(default=None, alias="x-oratoria-persona-token"),
    session_id: uuid.UUID | None = Query(default=None),
    db: DBSession = Depends(get_db),
) -> Any:
    _verify_token(x_oratoria_persona_token)

    system_prompt = await _resolve_system_prompt(session_id, body.messages, db)
    messages = [m.model_dump() for m in body.messages]

    agent = PersonaAgent()
    chunk_id = _make_chunk_id()

    if body.stream:

        async def event_generator():
            async for token in agent.astream_reply(system_prompt=system_prompt, messages=messages):
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            # Final chunk with finish_reason=stop
            final = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming: accumulate
    tokens: list[str] = []
    async for token in agent.astream_reply(system_prompt=system_prompt, messages=messages):
        tokens.append(token)
    content = "".join(tokens)
    return {
        "id": chunk_id,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
