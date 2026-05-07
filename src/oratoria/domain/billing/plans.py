"""Plan catalog."""

from __future__ import annotations

from typing import TypedDict

from oratoria.models.subscription import SubscriptionPlan


class PlanFeatures(TypedDict):
    sessions_per_month: int | None
    realtime_minutes: int | None
    pdf_reports: bool
    priority_support: bool


PLAN_CATALOG: dict[SubscriptionPlan, PlanFeatures] = {
    SubscriptionPlan.FREE: {
        "sessions_per_month": 3,
        "realtime_minutes": 30,
        "pdf_reports": False,
        "priority_support": False,
    },
    SubscriptionPlan.BASIC: {
        "sessions_per_month": 30,
        "realtime_minutes": 300,
        "pdf_reports": True,
        "priority_support": False,
    },
    SubscriptionPlan.PRO: {
        "sessions_per_month": None,
        "realtime_minutes": None,
        "pdf_reports": True,
        "priority_support": True,
    },
    SubscriptionPlan.ENTERPRISE: {
        "sessions_per_month": None,
        "realtime_minutes": None,
        "pdf_reports": True,
        "priority_support": True,
    },
}
