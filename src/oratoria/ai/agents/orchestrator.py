"""LangGraph orchestrator: transcribe → analyze paraverbal → evaluate → generate report."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from oratoria.ai.agents.evaluator import EvaluatorAgent
from oratoria.ai.parsers.feedback_schema import EvaluationReport, ParaverbalMetrics

if TYPE_CHECKING:
    pass


class SessionContext(TypedDict, total=False):
    presentation_type: str
    audience: str
    goal: str
    formality: str
    language: str


class OrchestratorState(TypedDict, total=False):
    audio_bytes: bytes
    transcript: str
    paraverbal_metrics: ParaverbalMetrics
    evaluation: EvaluationReport
    report_payload: dict[str, Any]
    context: SessionContext
    errors: list[str]


async def _transcribe_node(state: OrchestratorState) -> OrchestratorState:
    """Run STT over audio_bytes → transcript."""
    from oratoria.services.stt.whisper import WhisperSTT

    stt = WhisperSTT()
    result = await stt.transcribe(state["audio_bytes"], language=state.get("context", {}).get("language", "es"))
    return {"transcript": result.text}


async def _analyze_paraverbal_node(state: OrchestratorState) -> OrchestratorState:
    """Run paraverbal analyzer over audio bytes."""
    from oratoria.services.paraverbal.analyzer import ParaverbalAnalyzer

    analyzer = ParaverbalAnalyzer()
    metrics = await analyzer.analyze(state["audio_bytes"], transcript=state.get("transcript", ""))
    return {"paraverbal_metrics": metrics}


async def _evaluate_node(state: OrchestratorState) -> OrchestratorState:
    agent = EvaluatorAgent()
    ctx: SessionContext = state.get("context", {})
    evaluation = await agent.evaluate(
        transcript=state["transcript"],
        paraverbal_metrics=state["paraverbal_metrics"],
        presentation_type=ctx.get("presentation_type", "presentación general"),
        audience=ctx.get("audience", "audiencia mixta"),
        goal=ctx.get("goal", "comunicar con claridad y persuadir"),
        formality=ctx.get("formality", "profesional"),
        language=ctx.get("language", "es"),
    )
    return {"evaluation": evaluation}


async def _generate_report_node(state: OrchestratorState) -> OrchestratorState:
    evaluation = state["evaluation"]
    return {
        "report_payload": {
            "score": evaluation.score,
            "summary": evaluation.summary,
            "strengths": [s.model_dump() for s in evaluation.strengths],
            "improvements": [i.model_dump() for i in evaluation.improvements],
            "paraverbal_metrics": evaluation.paraverbal_metrics.model_dump(),
            "next_steps": evaluation.next_steps,
        }
    }


def build_orchestrator() -> Any:
    """Compile the LangGraph state machine for full session evaluation."""
    graph = StateGraph(OrchestratorState)
    graph.add_node("transcribe", _transcribe_node)
    graph.add_node("analyze_paraverbal", _analyze_paraverbal_node)
    graph.add_node("evaluate", _evaluate_node)
    graph.add_node("generate_report", _generate_report_node)

    graph.add_edge(START, "transcribe")
    graph.add_edge("transcribe", "analyze_paraverbal")
    graph.add_edge("analyze_paraverbal", "evaluate")
    graph.add_edge("evaluate", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()
