"""Query-parameter routing.

A single Streamlit page with `?view=` routing rather than st.navigation, because
topics are database rows that the instructor creates and renames at runtime —
there is no fixed page list to declare. It also makes every experiment a
shareable URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import streamlit as st

from hub import db

VIEWS = {"home", "topic", "experiment", "admin"}


@dataclass(frozen=True)
class Route:
    view: str
    topic_id: int | None
    experiment_id: str | None


def parse_route(params: Mapping[str, str]) -> Route:
    home = Route("home", None, None)

    if params.get("admin") == "1":
        return Route("admin", None, None)

    view = params.get("view", "home")
    if view not in VIEWS:
        return home

    if view == "topic":
        raw = params.get("topic")
        if raw is None:
            return home
        try:
            return Route("topic", int(raw), None)
        except (TypeError, ValueError):
            return home

    if view == "experiment":
        exp = params.get("exp")
        return Route("experiment", None, exp) if exp else home

    return home


def route_params(route: Route) -> dict[str, str]:
    if route.view == "admin":
        return {"admin": "1"}
    if route.view == "topic" and route.topic_id is not None:
        return {"view": "topic", "topic": str(route.topic_id)}
    if route.view == "experiment" and route.experiment_id:
        return {"view": "experiment", "exp": route.experiment_id}
    return {"view": "home"}


def go(route: Route) -> None:
    """Navigate, preserving the anonymous device id if one is in use."""
    device = st.query_params.get("d")
    params = route_params(route)
    if device:
        params["d"] = device
    st.query_params.clear()
    st.query_params.update(params)
    st.rerun()


def render_sidebar_nav(engine, route: Route) -> None:
    """Hub navigation above whatever the vendored module puts in the sidebar."""
    with st.sidebar:
        st.markdown("### ⚡ Course Modules")
        if st.button("Home", use_container_width=True, key="_hub.nav_home"):
            go(Route("home", None, None))

        for topic in db.list_topics(engine, include_disabled=False):
            experiments = db.list_experiments(
                engine, topic_id=topic["id"], include_disabled=False
            )
            if not experiments:
                continue
            with st.expander(topic["name"], expanded=route.topic_id == topic["id"]):
                for exp in experiments:
                    active = exp["experiment_id"] == route.experiment_id
                    label = ("▸ " if active else "") + exp["title"]
                    if st.button(
                        label, use_container_width=True,
                        key=f"_hub.nav_{exp['experiment_id']}",
                    ):
                        go(Route("experiment", None, exp["experiment_id"]))
        st.divider()
