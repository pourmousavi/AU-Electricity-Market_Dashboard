"""Renders one experiment: hub chrome, then the vendored dashboard verbatim.

Access is checked here, before the runner is called, so a disabled experiment's
code is never executed even if someone types its URL directly.
"""
from __future__ import annotations

import html
import logging

import streamlit as st

from hub import analytics, db, theme
from hub.catalogue import Experiment
from hub.router import Route, go
from hub.runner import ExperimentRenderError, render_experiment

OPEN_TS_KEY = "_hub.open_ts"
OPEN_EXP_KEY = "_hub.open_exp"

logger = logging.getLogger(__name__)


def resolve_access(row: dict | None, catalogue: dict[str, Experiment]) -> tuple[str, str]:
    """Decide whether this experiment may render."""
    if row is None:
        return "missing", "That experiment does not exist."
    if row.get("orphaned") or row["experiment_id"] not in catalogue:
        return "orphaned", "That experiment is no longer part of the course site."
    if not row.get("enabled"):
        return "disabled", "This experiment is not available yet."
    return "ok", ""


def close_previous(engine, current_experiment_id: str | None) -> None:
    """Emit a dwell event when the student leaves an experiment."""
    previous = st.session_state.get(OPEN_EXP_KEY)
    if previous and previous != current_experiment_id:
        opened_at = st.session_state.get(OPEN_TS_KEY)
        dwell = analytics.now_ms() - opened_at if opened_at else None
        analytics.track(
            engine, "experiment_close", experiment_id=previous, dwell_ms=dwell
        )
        analytics.flush(engine)
        st.session_state.pop(OPEN_EXP_KEY, None)
        st.session_state.pop(OPEN_TS_KEY, None)


def render_experiment_page(engine, experiment_id: str, catalogue: dict) -> None:
    row = db.get_experiment(engine, experiment_id)
    status, message = resolve_access(row, catalogue)

    if status != "ok":
        theme.inject(theme.dark_page_css())
        st.markdown(
            f"""<div class="hub-dark">
  <span class="hub-chip">🔒 Unavailable</span>
  <div class="hub-title" style="font-size:clamp(1.4rem,3vw,2rem)">{html.escape(message)}</div>
</div>""",
            unsafe_allow_html=True,
        )
        if st.button("← All topics", key="_hub.exp_denied_back"):
            go(Route("home", None, None))
        return

    topics = {t["id"]: t for t in db.list_topics(engine, include_disabled=True)}
    topic = topics.get(row["topic_id"]) or {"name": "Unassigned", "id": None}

    if st.session_state.get(OPEN_EXP_KEY) != experiment_id:
        st.session_state[OPEN_EXP_KEY] = experiment_id
        st.session_state[OPEN_TS_KEY] = analytics.now_ms()
        analytics.track(
            engine, "experiment_open",
            topic_id=topic.get("id"), experiment_id=experiment_id,
        )

    theme.inject(theme.experiment_header_css())
    st.markdown(
        f"""<div class="hub-expbar">
  <span class="crumb">{html.escape(topic['name'])}</span>
  <span class="dot">·</span>
  <span class="now">{html.escape(row['title'])}</span>
</div>""",
        unsafe_allow_html=True,
    )

    try:
        render_experiment(catalogue[experiment_id])
    except ExperimentRenderError as exc:
        # This page is public with no login -- students, not the coordinator,
        # are the audience. A full traceback (source paths, library internals,
        # local frames) must never render here. The detail goes to the server
        # log and to an analytics event the coordinator can see in the admin
        # panel instead.
        logger.exception("experiment %s failed to render", experiment_id)
        analytics.track(engine, "experiment_error", experiment_id=experiment_id)
        st.error(
            "This experiment could not be loaded. The problem has been "
            "reported automatically."
        )
