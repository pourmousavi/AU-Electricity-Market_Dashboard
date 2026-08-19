"""Presentation state: topics, experiment placement, and analytics storage.

SQLAlchemy Core rather than raw SQL so the same DDL runs on Neon Postgres in
production and in-memory SQLite in the tests.
"""
from __future__ import annotations

from typing import Any

import streamlit as st
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table,
    Text, create_engine, delete, func, insert, select, update,
)
from sqlalchemy.engine import Engine

from hub.catalogue import Experiment

metadata = MetaData()

topic = Table(
    "topic", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(120), nullable=False),
    Column("subtitle", Text, nullable=False, default=""),
    Column("unlock_message", Text, nullable=False, default=""),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("enabled", Boolean, nullable=False, default=True),
)

experiment = Table(
    "experiment", metadata,
    Column("experiment_id", String(120), primary_key=True),
    Column("topic_id", Integer, ForeignKey("topic.id"), nullable=True),
    Column("title", String(200), nullable=False),
    Column("blurb", Text, nullable=False, default=""),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("enabled", Boolean, nullable=False, default=False),
    Column("orphaned", Boolean, nullable=False, default=False),
)

visitor_session = Table(
    "visitor_session", metadata,
    Column("id", String(80), primary_key=True),
    Column("ip_hash", String(64), nullable=True),
    Column("user_agent", Text, nullable=True),
    Column("referrer", Text, nullable=True),
    Column("first_seen", DateTime(timezone=True), server_default=func.now()),
)

event = Table(
    "event", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(80), nullable=True),
    Column("ts", DateTime(timezone=True), server_default=func.now()),
    Column("kind", String(40), nullable=False),
    Column("topic_id", Integer, nullable=True),
    Column("experiment_id", String(120), nullable=True),
    Column("dwell_ms", Integer, nullable=True),
)

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    """Engine for the configured Neon database."""
    return create_engine(st.secrets["neon"]["dsn"], pool_pre_ping=True)


def bootstrap(engine: Engine) -> None:
    metadata.create_all(engine)


# An id is a lower-case module name, so `.title()` alone turns every acronym in
# one into a word: "Lp Vertex Walk", "Dc Opf Results". These stay upper-case.
# The title is only a starting point either way, editable per experiment in the
# admin panel, and reconcile never rewrites one that already exists.
ACRONYMS = frozenset({"lp", "dc", "opf"})


def _default_title(experiment_id: str) -> str:
    return " ".join(
        word.upper() if word in ACRONYMS else word.title()
        for word in experiment_id.split("_")
    )


def seed_initial(engine: Engine, catalogue: dict[str, Experiment]) -> bool:
    """Park every experiment in one disabled topic for the admin to sort.

    An experiment module carries no opinion about where it belongs on the
    site, so there is nothing to derive a topic layout from -- the layout is
    the coordinator's, made in the admin panel. The seed just makes sure
    nothing is invisible there, and reaches no student until it is placed
    deliberately.

    Only runs on a genuinely first-boot, empty database: both the topic
    table AND the experiment table must be empty. `delete_topic` deletes
    topics but deliberately keeps their experiments (unassigned, disabled),
    so a topic table emptied that way must not be mistaken for first boot --
    doing so would re-insert existing experiment ids and crash on the
    primary key. Returns True if it seeded.
    """
    with engine.begin() as conn:
        topic_count = conn.execute(select(func.count()).select_from(topic)).scalar_one()
        experiment_count = conn.execute(
            select(func.count()).select_from(experiment)
        ).scalar_one()
        if topic_count > 0 or experiment_count > 0:
            return False

        result = conn.execute(insert(topic).values(
            name="Unsorted", subtitle="Assign these to topics in the admin panel.",
            unlock_message="Not available yet.", sort_order=0, enabled=False,
        ))
        unsorted_id = int(result.inserted_primary_key[0])

        for order, exp in enumerate(catalogue.values()):
            conn.execute(insert(experiment).values(
                experiment_id=exp.id, topic_id=unsorted_id,
                title=_default_title(exp.id), blurb="",
                sort_order=order, enabled=False, orphaned=False,
            ))
    return True


def reconcile(engine: Engine, catalogue: dict[str, Experiment]) -> tuple[int, int]:
    """Sync DB rows with the catalogue. Returns (inserted, newly orphaned).

    New catalogue ids arrive unassigned and disabled, so nothing reaches
    students until it is deliberately placed. Ids that vanish from the
    catalogue are flagged, never deleted.
    """
    inserted = orphaned = 0
    with engine.begin() as conn:
        known = {r[0] for r in conn.execute(select(experiment.c.experiment_id))}

        for exp_id in catalogue:
            if exp_id not in known:
                conn.execute(insert(experiment).values(
                    experiment_id=exp_id, topic_id=None,
                    title=_default_title(exp_id), blurb="",
                    sort_order=0, enabled=False, orphaned=False,
                ))
                inserted += 1

        for exp_id in known:
            if exp_id not in catalogue:
                result = conn.execute(
                    update(experiment)
                    .where(experiment.c.experiment_id == exp_id,
                           experiment.c.orphaned.is_(False))
                    .values(orphaned=True)
                )
                orphaned += result.rowcount or 0

        # An id that came back is no longer orphaned.
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id.in_(list(catalogue)))
            .values(orphaned=False)
        )
    return inserted, orphaned


def _rows(result) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in result]


def list_topics(engine: Engine, include_disabled: bool) -> list[dict[str, Any]]:
    stmt = select(topic).order_by(topic.c.sort_order, topic.c.id)
    if not include_disabled:
        stmt = stmt.where(topic.c.enabled.is_(True))
    with engine.connect() as conn:
        return _rows(conn.execute(stmt))


def list_experiments(
    engine: Engine, topic_id: int | None, include_disabled: bool
) -> list[dict[str, Any]]:
    """Experiments, optionally scoped to one topic.

    `topic_id=None` means every topic. Orphaned rows are only ever returned
    when include_disabled is True (i.e. to the admin).
    """
    stmt = select(experiment).order_by(experiment.c.sort_order, experiment.c.experiment_id)
    if topic_id is not None:
        stmt = stmt.where(experiment.c.topic_id == topic_id)
    if not include_disabled:
        stmt = stmt.where(
            experiment.c.enabled.is_(True), experiment.c.orphaned.is_(False)
        )
    with engine.connect() as conn:
        return _rows(conn.execute(stmt))


def get_experiment(engine: Engine, experiment_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(experiment).where(experiment.c.experiment_id == experiment_id)
        ).first()
    return dict(row._mapping) if row else None


def set_experiment_enabled(engine: Engine, experiment_id: str, enabled: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(enabled=enabled)
        )


def set_topic_enabled(engine: Engine, topic_id: int, enabled: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(topic).where(topic.c.id == topic_id).values(enabled=enabled)
        )


def assign_experiment(
    engine: Engine, experiment_id: str, topic_id: int | None, sort_order: int
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(topic_id=topic_id, sort_order=sort_order)
        )


def update_experiment_text(
    engine: Engine, experiment_id: str, title: str, blurb: str
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(title=title, blurb=blurb)
        )


def upsert_topic(
    engine: Engine, topic_id: int | None, name: str, subtitle: str,
    unlock_message: str, sort_order: int, enabled: bool,
) -> int:
    values = dict(
        name=name, subtitle=subtitle, unlock_message=unlock_message,
        sort_order=sort_order, enabled=enabled,
    )
    with engine.begin() as conn:
        if topic_id is None:
            result = conn.execute(insert(topic).values(**values))
            return int(result.inserted_primary_key[0])
        conn.execute(update(topic).where(topic.c.id == topic_id).values(**values))
        return topic_id


def delete_topic(engine: Engine, topic_id: int) -> None:
    """Remove a topic; its experiments become unassigned rather than vanishing."""
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.topic_id == topic_id)
            .values(topic_id=None, enabled=False)
        )
        conn.execute(delete(topic).where(topic.c.id == topic_id))
