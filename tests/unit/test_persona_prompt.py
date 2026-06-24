"""Tests for persona_prompt.py — pure function, no mocks needed."""
from __future__ import annotations
import pytest
from oratoria.ai.prompts.persona_prompt import build_persona_system_prompt


class TestBuildPersonaSystemPrompt:
    def test_education_segment_contains_academic_text(self):
        result = build_persona_system_prompt(
            segment="education", presentation_type="tesis", audience="jurado",
            objective="defender", formality="alta", duration_target=10,
            interactive=False, user_full_name="Ana López",
        )
        assert "comité académico" in result

    def test_business_segment_contains_executive_text(self):
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="inversores",
            objective="captar fondos", formality="alta", duration_target=5,
            interactive=False, user_full_name="Carlos Ruiz",
        )
        assert "ejecutivo o inversionista" in result

    def test_hr_segment_contains_recruiter_text(self):
        result = build_persona_system_prompt(
            segment="hr", presentation_type="entrevista", audience="reclutador",
            objective="conseguir trabajo", formality="media", duration_target=15,
            interactive=False, user_full_name="María García",
        )
        assert "reclutador o gerente" in result

    def test_formality_alta_in_result(self):
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="board",
            objective="convencer", formality="alta", duration_target=5,
            interactive=False, user_full_name="Pedro Ruiz",
        )
        assert "formal, profesional" in result

    def test_formality_media_in_result(self):
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="equipo",
            objective="actualizar", formality="media", duration_target=5,
            interactive=False, user_full_name="Laura Soto",
        )
        assert "cordial y profesional" in result

    def test_audience_and_objective_in_result(self):
        result = build_persona_system_prompt(
            segment="education", presentation_type="seminario", audience="comité de ética",
            objective="aprobar protocolo", formality="alta", duration_target=20,
            interactive=False, user_full_name="Juan Torres",
        )
        assert "comité de ética" in result
        assert "aprobar protocolo" in result

    def test_base_rules_guardrail_present(self):
        """The base rules contain the silence-while-presenting guardrail."""
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="socios",
            objective="informar", formality="media", duration_target=5,
            interactive=False, user_full_name="Sofía Lima",
        )
        assert "Mantente en silencio mientras la persona expone" in result

    def test_interactive_override_present_when_true(self):
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="clientes",
            objective="vender", formality="media", duration_target=5,
            interactive=True, user_full_name="Diego Mora",
        )
        assert "Modo interactivo (override)" in result

    def test_interactive_override_absent_when_false(self):
        result = build_persona_system_prompt(
            segment="business", presentation_type="pitch", audience="clientes",
            objective="vender", formality="media", duration_target=5,
            interactive=False, user_full_name="Diego Mora",
        )
        assert "Modo interactivo (override)" not in result
