"""
F1-A (behavioral) + SPK-03 (latencia) — Persona Agent con LLM real.

Construye el prompt de persona para un brief, simula que el orador terminó
su presentación, y verifica que el agente genere una pregunta de audiencia
coherente y en tono. Mide time-to-first-token y latencia total.

Uso:
  uv run --no-sync python scripts/f1_persona_behavioral.py
"""

from __future__ import annotations

import asyncio
import time

from oratoria.ai.agents.persona import PersonaAgent
from oratoria.ai.prompts.persona_prompt import build_persona_system_prompt

# Tres briefs, uno por segmento, para validar el tono.
CASES = [
    dict(
        label="EDUCATIVO · tesis · formalidad alta",
        segment="education",
        presentation_type="tesis",
        audience="comité de tesis de cinco profesores",
        objective="convencer al jurado de la viabilidad de mi proyecto",
        formality="alta",
        duration_target=5,
        interactive=False,
        user_full_name="María",
    ),
    dict(
        label="EMPRESARIAL · pitch · formalidad media",
        segment="business",
        presentation_type="pitch",
        audience="inversores de una ronda semilla",
        objective="cerrar la inversión",
        formality="media",
        duration_target=3,
        interactive=False,
        user_full_name="María",
    ),
]

USER_TURN = (
    "Buenos días. Hoy les presento mi proyecto: una plataforma que usa "
    "inteligencia artificial para entrenar la oratoria con feedback en "
    "tiempo real. Creo que puede ayudar a mucha gente. Bueno, eso es todo, "
    "muchas gracias por su atención."
)


async def run_case(case: dict) -> None:
    label = case.pop("label")
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    system_prompt = build_persona_system_prompt(**case)
    agent = PersonaAgent()
    messages = [{"role": "user", "content": USER_TURN}]

    t0 = time.perf_counter()
    ttft = None
    chunks: list[str] = []
    async for tok in agent.astream_reply(system_prompt=system_prompt, messages=messages):
        if ttft is None:
            ttft = time.perf_counter() - t0
        chunks.append(tok)
        print(tok, end="", flush=True)
    total = time.perf_counter() - t0

    print(f"\n\n--- TTFT: {ttft*1000:.0f} ms | total: {total*1000:.0f} ms | "
          f"chars: {sum(len(c) for c in chunks)} ---")


async def main() -> None:
    for case in CASES:
        await run_case(case)


if __name__ == "__main__":
    asyncio.run(main())
