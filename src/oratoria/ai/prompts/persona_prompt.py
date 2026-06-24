"""Persona system prompt builder for the Audiencia Digital LLM endpoint.

Thin wrapper around ``build_audience_context`` from ``audience_prompt``.
The function is named ``build_persona_system_prompt`` to make its role in
the persona-LLM pipeline explicit; the underlying logic is identical.
"""

from __future__ import annotations

from oratoria.ai.prompts.audience_prompt import build_audience_context


def build_persona_system_prompt(
    *,
    segment: str | None,
    presentation_type: str | None,
    audience: str | None,
    objective: str | None,
    formality: str | None,
    duration_target: int | float | None,
    interactive: bool,
    user_full_name: str | None = None,
) -> str:
    """Compose the system prompt for the Persona LLM (Audiencia Digital).

    Delegates entirely to ``build_audience_context`` — same args, same output.
    """
    return build_audience_context(
        segment=segment,
        presentation_type=presentation_type,
        audience=audience,
        objective=objective,
        formality=formality,
        duration_target=duration_target,
        interactive=interactive,
        user_full_name=user_full_name,
    )


__all__ = ["build_persona_system_prompt"]
