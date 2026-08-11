"""Executes one experiment out of a vendored dashboard, unmodified.

Two isolation modes, both of which guarantee that only the selected
experiment's code runs:

  pin_selectbox — Weeks 2/3/4 each call `st.sidebar.selectbox` exactly once at
    module level and dispatch on the result with `if page == ...`. We make that
    one call return the experiment we want, then execute the file. Exactly one
    branch runs.

  pin_tab — Weeks 6/7/8 build their content inside `with tabN:` blocks whose
    bodies are partly inline code, so calling render functions is not enough.
    We blank the unselected bodies in the AST (see hub.tabsurgery) and patch
    st.tabs to draw a single tab.

Never edit anything under sources/.
"""
from __future__ import annotations

import contextlib
import types
from pathlib import Path
from types import CodeType

import streamlit as st

from hub.catalogue import Experiment
from hub.state import isolate
from hub.tabsurgery import TabSurgeryError, select_tab


class ExperimentRenderError(Exception):
    """An experiment could not be rendered from its source."""


@contextlib.contextmanager
def _no_page_config():
    """Vendored modules all call st.set_page_config; only the hub may."""
    original = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None
    try:
        yield
    finally:
        st.set_page_config = original


@contextlib.contextmanager
def _pinned_selectbox(selector: str):
    """Force the module's single nav dropdown to return `selector`.

    Only the first call is intercepted — inner `st.selectbox` calls in the main
    area are untouched, and any later sidebar dropdown behaves normally.
    """
    original = st.sidebar.selectbox
    used = {"value": False}

    def shim(label, options, *args, **kwargs):
        if used["value"]:
            return original(label, options, *args, **kwargs)
        used["value"] = True
        if selector not in list(options):
            raise ExperimentRenderError(
                f"{selector!r} is not among the options {list(options)!r}"
            )
        return selector

    st.sidebar.selectbox = shim
    try:
        yield
    finally:
        st.sidebar.selectbox = original


@contextlib.contextmanager
def _pinned_tabs(index: int, selector: str):
    """Draw a single tab, and hand back nullcontexts for the blanked ones."""
    original = st.tabs

    def shim(labels, *args, **kwargs):
        real = original([selector], *args, **kwargs)[0]
        out: list = [contextlib.nullcontext() for _ in labels]
        out[index] = real
        return out

    st.tabs = shim
    try:
        yield
    finally:
        st.tabs = original


@st.cache_resource(show_spinner=False)
def prepare(source_path: str, mode: str, selector: str) -> tuple[CodeType, int]:
    """Compile a source for one experiment. Cached per (file, mode, selector).

    Returns the code object and the selected tab index (-1 for pin_selectbox).
    """
    path = Path(source_path)
    source = path.read_text(encoding="utf-8")

    if mode == "pin_selectbox":
        return compile(source, str(path), "exec"), -1

    if mode == "pin_tab":
        try:
            tree, index = select_tab(source, selector)
        except TabSurgeryError as exc:
            raise ExperimentRenderError(f"{path.name}: {exc}") from exc
        return compile(tree, str(path), "exec"), index

    raise ExperimentRenderError(f"unknown mode {mode!r}")


def render_experiment(exp: Experiment) -> None:
    """Render one experiment into the current Streamlit context."""
    isolate(st.session_state, exp.source_key)
    code, index = prepare(str(exp.source_path), exp.mode, exp.selector)

    module = types.ModuleType("_hub_vendored")
    module.__file__ = str(exp.source_path)
    module.__dict__["__name__"] = "_hub_vendored"  # keeps __main__ guards shut

    with _no_page_config():
        if exp.mode == "pin_selectbox":
            with _pinned_selectbox(exp.selector):
                exec(code, module.__dict__)
        else:
            with _pinned_tabs(index, exp.selector):
                exec(code, module.__dict__)
                if exp.entry == "main":
                    entry = module.__dict__.get("main")
                    if not callable(entry):
                        raise ExperimentRenderError(
                            f"{exp.id}: source has no callable main()"
                        )
                    entry()
