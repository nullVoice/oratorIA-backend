"""Session status state machine."""

from __future__ import annotations

from oratoria.models.session import SessionStatus

ALLOWED_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.PENDING: {SessionStatus.IN_PROGRESS, SessionStatus.CANCELED},
    SessionStatus.IN_PROGRESS: {SessionStatus.PROCESSING, SessionStatus.CANCELED},
    SessionStatus.PROCESSING: {SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: {SessionStatus.PROCESSING},
    SessionStatus.CANCELED: set(),
}


def can_transition(current: SessionStatus, target: SessionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
