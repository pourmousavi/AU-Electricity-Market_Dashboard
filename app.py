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
        admin.render(engine, catalogue)
        return

    analytics.ensure_session(engine)
    pages_experiment.close_previous(
        engine, route.experiment_id if route.view == "experiment" else None
    )
    render_sidebar_nav(engine, route)

    if route.view == "topic" and route.topic_id is not None:
        analytics.track(engine, "topic_view", topic_id=route.topic_id)
        pages_student.render_topic(engine, route.topic_id)
    elif route.view == "experiment" and route.experiment_id:
        pages_experiment.render_experiment_page(engine, route.experiment_id, catalogue)
    else:
        analytics.track(engine, "home_view")
        pages_student.render_home(engine)

    analytics.flush(engine)


main()
