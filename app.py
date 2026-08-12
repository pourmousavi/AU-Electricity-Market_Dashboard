"""Electricity Market Course — unified dashboard hub.

Entry point: sets up the page, reconciles the catalogue against the database,
and dispatches on the query-string route.
"""
from __future__ import annotations

import streamlit as st

from hub import analytics, admin, db, pages_experiment, pages_student
from hub.catalogue import load_catalogue
from hub.router import parse_route, render_sidebar_nav

st.set_page_config(
    page_title="Electricity Market & Power Systems Operation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _startup():
    """Bootstrap, seed and reconcile exactly once per app boot."""
    catalogue = load_catalogue()
    engine = db.get_engine()
    db.bootstrap(engine)
    db.seed_initial(engine, catalogue)
    db.reconcile(engine, catalogue)
    return engine, catalogue


def main() -> None:
    engine, catalogue = _startup()
    route = parse_route(st.query_params)

    if route.view == "admin":
        # A student may navigate straight from an open experiment to
        # ?admin=1. Close out any open-experiment dwell bookkeeping before
        # returning, or the next real experiment_close absorbs the entire
        # admin-panel visit as reading time. Do NOT call ensure_session
        # here -- an admin visit must not be counted as a student session.
        pages_experiment.close_previous(engine, None)
        admin.render(engine, catalogue)
        return

    analytics.ensure_session(engine)
    pages_experiment.close_previous(
        engine, route.experiment_id if route.view == "experiment" else None
    )
    render_sidebar_nav(engine, route)

    # try/finally, not try/except: an unhandled exception from a render call
    # must still propagate so Streamlit shows its own error -- this only
    # guarantees the analytics buffer is flushed either way, closing the
    # small window where a mid-render crash would otherwise leave buffered
    # events sitting in session state until the next successful rerun.
    try:
        if route.view == "topic" and route.topic_id is not None:
            analytics.track(engine, "topic_view", topic_id=route.topic_id)
            pages_student.render_topic(engine, route.topic_id)
        elif route.view == "experiment" and route.experiment_id:
            pages_experiment.render_experiment_page(engine, route.experiment_id, catalogue)
        else:
            analytics.track(engine, "home_view")
            pages_student.render_home(engine)
    finally:
        analytics.flush(engine)


main()
