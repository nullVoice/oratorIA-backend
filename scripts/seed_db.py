"""Seed the database with test data.

Creates 3 users (one per segment), 5 sessions each across varied
statuses, and a report for every COMPLETED session.

Usage:
    uv run --no-sync python scripts/seed_db.py            # safe: refuses if data exists
    uv run --no-sync python scripts/seed_db.py --force    # TRUNCATE first, then seed
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from oratoria.core.security import hash_password
from oratoria.database import async_engine, async_session_factory
from oratoria.models import Report, Session, User
from oratoria.models.session import SessionStatus, SessionType
from oratoria.models.user import UserSegment

SEGMENTS: list[tuple[str, str, UserSegment]] = [
    ("alice@school.edu", "Alice Educator", UserSegment.EDUCATION),
    ("bob@corp.com", "Bob Manager", UserSegment.BUSINESS),
    ("carol@hr.com", "Carol HR", UserSegment.HR),
]

# 5 sessions per user, varied states.
SESSION_STATES: list[SessionStatus] = [
    SessionStatus.CREATED,
    SessionStatus.IN_PROGRESS,
    SessionStatus.PROCESSING,
    SessionStatus.COMPLETED,
    SessionStatus.COMPLETED,
]

DEFAULT_PASSWORD = "changeme123"


async def truncate_all() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE TABLE "
            "audit_logs, reports, transcripts, sessions, "
            "subscriptions, progress, users "
            "RESTART IDENTITY CASCADE"
        ))


async def seed() -> tuple[int, int, int]:
    sessions_created = 0
    reports_created = 0
    async with async_session_factory() as s:
        users: list[User] = []
        for email, name, segment in SEGMENTS:
            u = User(
                email=email,
                hashed_password=hash_password(DEFAULT_PASSWORD),
                full_name=name,
                segment=segment,
                is_active=True,
                is_verified=True,
            )
            s.add(u)
            users.append(u)
        await s.flush()

        for u in users:
            for i, status in enumerate(SESSION_STATES):
                started = datetime.now(timezone.utc) - timedelta(days=5 - i)
                has_started = status != SessionStatus.CREATED
                has_ended = status in (SessionStatus.COMPLETED, SessionStatus.FAILED)
                sess = Session(
                    user_id=u.id,
                    type=SessionType.ASYNC,
                    status=status,
                    context={
                        "presentation_type": "pitch",
                        "audience": "investors",
                        "objective": "convencer al inversor",
                        "formality": "alta",
                        "duration_target": 5,
                    },
                    started_at=started if has_started else None,
                    ended_at=started + timedelta(minutes=5) if has_ended else None,
                    duration_seconds=300 if has_ended else None,
                )
                s.add(sess)
                sessions_created += 1
                await s.flush()

                if status == SessionStatus.COMPLETED:
                    s.add(Report(
                        session_id=sess.id,
                        score=70 + (i * 5),
                        summary=(
                            f"Sesión {i + 1} de {u.full_name}. "
                            "Buena estructura general; ritmo adecuado y postura segura."
                        ),
                        strengths=[
                            {
                                "title": "Apertura clara",
                                "dimension": "verbal",
                                "evidence": "Saludo y propósito en menos de 30s",
                                "impact": "La audiencia identifica el tema rápido",
                            },
                        ],
                        improvements=[
                            {
                                "title": "Reducir muletillas",
                                "dimension": "paraverbal",
                                "evidence": "5 'ehs' en el primer minuto",
                                "suggestion": "Practicar pausas conscientes en lugar de rellenar",
                                "priority": "medium",
                            },
                        ],
                        paraverbal_metrics={
                            "words_per_minute": 130.0,
                            "filler_words_count": 5,
                            "pause_ratio": 0.12,
                            "tone_variance": 0.25,
                        },
                        next_steps=[
                            "Practicar la apertura sin notas",
                            "Grabar y revisar pausas conscientes",
                        ],
                    ))
                    reports_created += 1
        await s.commit()
    return len(users), sessions_created, reports_created


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="TRUNCATE existing tables before seeding (otherwise refuse if data exists).",
    )
    args = parser.parse_args()

    async with async_session_factory() as s:
        existing = await s.scalar(select(func.count(User.id)))

    if existing and not args.force:
        print(
            f"Refusing to seed: database already has {existing} users. "
            "Re-run with --force to TRUNCATE and reseed."
        )
        await async_engine.dispose()
        return 1

    if existing:
        await truncate_all()

    users, sessions, reports = await seed()
    print(f"Seeded: users={users}, sessions={sessions}, reports={reports}")
    await async_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
