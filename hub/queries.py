"""Read-side analytics queries for the admin panel.

Medians are computed in Python rather than SQL so the same code runs on both
SQLite (tests) and Postgres (production).
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from hub import db


def _cutoff(days: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


def usage_summary(engine: Engine, days: int) -> dict[str, int]:
    since = _cutoff(days)
    with engine.connect() as conn:
        unique_visitors = conn.execute(
            select(func.count(func.distinct(db.visitor_session.c.ip_hash)))
            .where(db.visitor_session.c.first_seen >= since)
        ).scalar_one()
        sessions = conn.execute(
            select(func.count()).select_from(db.visitor_session)
            .where(db.visitor_session.c.first_seen >= since)
        ).scalar_one()
        opens = conn.execute(
            select(func.count()).select_from(db.event)
            .where(db.event.c.kind == "experiment_open", db.event.c.ts >= since)
        ).scalar_one()
    return {
        "unique_visitors": int(unique_visitors or 0),
        "sessions": int(sessions or 0),
        "experiment_opens": int(opens or 0),
    }


def experiment_ranking(engine: Engine, days: int) -> list[dict[str, Any]]:
    since = _cutoff(days)
    with engine.connect() as conn:
        opens = dict(conn.execute(
            select(db.event.c.experiment_id, func.count())
            .where(db.event.c.kind == "experiment_open", db.event.c.ts >= since)
            .group_by(db.event.c.experiment_id)
        ).all())

        dwells: dict[str, list[int]] = {}
        for exp_id, dwell in conn.execute(
            select(db.event.c.experiment_id, db.event.c.dwell_ms)
            .where(db.event.c.kind == "experiment_close",
                   db.event.c.ts >= since,
                   db.event.c.dwell_ms.is_not(None))
        ).all():
            dwells.setdefault(exp_id, []).append(int(dwell))

        titles = dict(conn.execute(
            select(db.experiment.c.experiment_id, db.experiment.c.title)
        ).all())

    rows = [
        {
            "experiment_id": exp_id,
            "title": titles.get(exp_id, exp_id),
            "opens": int(count),
            "median_dwell_s": (
                round(statistics.median(dwells[exp_id]) / 1000, 1)
                if dwells.get(exp_id) else None
            ),
        }
        for exp_id, count in opens.items()
    ]
    return sorted(rows, key=lambda r: r["opens"], reverse=True)


def events_dataframe(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.DataFrame(
            [dict(r._mapping) for r in conn.execute(select(db.event))]
        )
