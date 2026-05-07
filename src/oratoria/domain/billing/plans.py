"""Plan catalog."""

from __future__ import annotations

from typing import TypedDict

from oratoria.models.user import UserPlan


class PlanFeatures(TypedDict):
    sessions_per_month: int | None
    realtime_minutes: int | None
    pdf_reports: bool
    priority_support: bool


PLAN_CATALOG: dict[UserPlan, PlanFeatures] = {
    UserPlan.FREE: {
        "sessions_per_month": 3,
        "realtime_minutes": 30,
        "pdf_reports": False,
        "priority_support": False,
    },
    UserPlan.PRO: {
        "sessions_per_month": None,
        "realtime_minutes": None,
        "pdf_reports": True,
        "priority_support": True,
    },
    UserPlan.INSTITUTIONAL: {
        "sessions_per_month": None,
        "realtime_minutes": None,
        "pdf_reports": True,
        "priority_support": True,
    },
}
