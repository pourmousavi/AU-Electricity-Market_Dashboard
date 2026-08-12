"""Unit tests for the runner.

Every experiment is now its own module in experiments/ exposing render(), so
the runner has no patching primitives left to test: no pinned selectbox, no
pinned tabs, no set_page_config shim, and therefore no global render lock.
What remains is import, state-group namespacing, and error surfacing.

Full end-to-end rendering of all 25 experiments lives in
tests/test_experiments_render.py.
"""
import sys
import types

import pytest
import streamlit as st

from hub.catalogue import Experiment, load_catalogue
from hub.runner import ExperimentRenderError, render_experiment
from hub.state import ACTIVE_SOURCE_KEY


@pytest.fixture(autouse=True)
def _clean_session_state():
    """Bare-mode st.session_state is process-global; don't leak between tests."""
    st.session_state.pop(ACTIVE_SOURCE_KEY, None)
    yield
    st.session_state.pop(ACTIVE_SOURCE_KEY, None)


def _fake_module(name: str, **attributes) -> str:
    """Register a stand-in experiment module and return its qualified name."""
    qualified = f"experiments.{name}"
    module = types.ModuleType(qualified)
    module.render = lambda: None
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[qualified] = module
    return qualified


def test_missing_module_raises_render_error(tmp_path) -> None:
    exp = Experiment(id="does_not_exist", path=tmp_path / "does_not_exist.py")
    with pytest.raises(ExperimentRenderError, match="import failed"):
        render_experiment(exp)


def test_module_without_render_raises() -> None:
    module = types.ModuleType("experiments.no_render")
    sys.modules["experiments.no_render"] = module
    try:
        exp = Experiment(id="no_render", path=__file__)
        with pytest.raises(ExperimentRenderError, match="no callable render"):
            render_experiment(exp)
    finally:
        del sys.modules["experiments.no_render"]


def test_state_group_namespaces_session_state() -> None:
    qualified = _fake_module("grouped", STATE_GROUP="dispatch")
    try:
        render_experiment(Experiment(id="grouped", path=__file__))
        assert st.session_state[ACTIVE_SOURCE_KEY] == "dispatch"
    finally:
        del sys.modules[qualified]


def test_state_group_defaults_to_the_experiment_id() -> None:
    """A standalone experiment with no declared group owns its own namespace."""
    qualified = _fake_module("ungrouped")
    try:
        render_experiment(Experiment(id="ungrouped", path=__file__))
        assert st.session_state[ACTIVE_SOURCE_KEY] == "ungrouped"
    finally:
        del sys.modules[qualified]


def test_siblings_in_one_state_group_keep_each_others_state() -> None:
    """The five dispatch experiments share a _kit page and must share state.

    A student who configures generators in one week-7 experiment still has
    them in the next -- that is what STATE_GROUP buys, and it is the behaviour
    the source-file-keyed isolation used to give for free.
    """
    first = _fake_module("group_sibling_a", STATE_GROUP="dispatch")
    second = _fake_module("group_sibling_b", STATE_GROUP="dispatch")
    try:
        render_experiment(Experiment(id="group_sibling_a", path=__file__))
        st.session_state["generators"] = [1, 2, 3]
        render_experiment(Experiment(id="group_sibling_b", path=__file__))
        assert st.session_state["generators"] == [1, 2, 3]
    finally:
        st.session_state.pop("generators", None)
        del sys.modules[first]
        del sys.modules[second]


def test_switching_state_group_clears_foreign_keys() -> None:
    """Two unrelated experiments must not hand each other incompatible state."""
    dispatch = _fake_module("group_dispatch", STATE_GROUP="dispatch")
    network = _fake_module("group_network", STATE_GROUP="dc_network")
    try:
        render_experiment(Experiment(id="group_dispatch", path=__file__))
        st.session_state["generators"] = [1, 2, 3]
        render_experiment(Experiment(id="group_network", path=__file__))
        assert "generators" not in st.session_state
    finally:
        st.session_state.pop("generators", None)
        del sys.modules[dispatch]
        del sys.modules[network]


def test_every_catalogued_experiment_is_importable_and_renderable() -> None:
    """The catalogue is a directory listing, so nothing validates it but this."""
    import importlib

    for exp_id in load_catalogue():
        module = importlib.import_module(f"experiments.{exp_id}")
        assert callable(getattr(module, "render", None)), (
            f"{exp_id} has no callable render()"
        )
