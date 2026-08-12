"""Renders one experiment module.

Each experiment is its own module in experiments/ exposing render(), so there
is nothing to isolate at runtime: no monkeypatching of the shared streamlit
module, and therefore no global lock serialising concurrent students.

Session state is still namespaced, because separate modules can pick the same
key -- `supply_bids` means different things in different experiments. Modules
that deliberately share state (the ones backed by a common experiments/_kit
page) declare the same STATE_GROUP.
"""
from __future__ import annotations

import importlib

import streamlit as st

from hub.catalogue import Experiment
from hub.state import isolate


class ExperimentRenderError(Exception):
    """An experiment could not be rendered."""


def render_experiment(exp: Experiment) -> None:
    """Render one experiment into the current Streamlit context."""
    try:
        module = importlib.import_module(f"experiments.{exp.id}")
    except Exception as exc:  # noqa: BLE001 - surfaced as a hub-level error
        raise ExperimentRenderError(f"{exp.id}: import failed: {exc}") from exc

    isolate(st.session_state, getattr(module, "STATE_GROUP", exp.id))

    render = getattr(module, "render", None)
    if not callable(render):
        raise ExperimentRenderError(f"{exp.id}: module has no callable render()")
    render()
