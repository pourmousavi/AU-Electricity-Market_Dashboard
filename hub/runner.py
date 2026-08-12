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
import threading
import types
from pathlib import Path
from types import CodeType

import streamlit as st

from hub.catalogue import Experiment
from hub.state import isolate
from hub.tabsurgery import TabSurgeryError, select_tab

# Streamlit runs one thread per browser session against a single process-wide
# `streamlit` module, and takes no global script lock. The shims below patch
# that shared module, and the window they are installed for spans the entire
# exec() of a vendored dashboard -- seconds, once a PyPSA or cvxpy solve is in
# it. Two students in the same tutorial therefore overlap as a matter of
# course, not as a rare race.
#
# Two independent defences, because neither is sufficient alone:
#
#   1. This lock, held across the whole patched block, so shims never nest.
#      Without it, session B captures session A's *shim* as its "original" and
#      faithfully reinstalls it on exit -- permanently. Every later session in
#      the process then gets A's shim: a stale pin_tab index that raises
#      IndexError out of hub.admin's three-label st.tabs call, or a
#      set_page_config no-op that silently drops layout="wide".
#
#   2. An owner-thread check inside each shim, so a session that calls
#      st.tabs / st.sidebar.selectbox / st.set_page_config while another
#      session holds the lock gets the genuine function rather than someone
#      else's pin.
_RENDER_LOCK = threading.RLock()


class ExperimentRenderError(Exception):
    """An experiment could not be rendered from its source."""


@contextlib.contextmanager
def _no_page_config():
    """Vendored modules all call st.set_page_config; only the hub may."""
    original = st.set_page_config
    owner = threading.get_ident()

    def shim(*args, **kwargs):
        if threading.get_ident() != owner:
            return original(*args, **kwargs)
        return None

    st.set_page_config = shim
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
    owner = threading.get_ident()
    used = {"value": False}

    def shim(label, options, *args, **kwargs):
        # Another session's call must neither be pinned to this experiment nor
        # consume this experiment's one-shot interception.
        if threading.get_ident() != owner or used["value"]:
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
    owner = threading.get_ident()

    def shim(labels, *args, **kwargs):
        if threading.get_ident() != owner:
            return original(labels, *args, **kwargs)
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

    # Serialised: the shims patch the process-global streamlit module, so two
    # concurrent sessions must never have them installed at the same time.
    with _RENDER_LOCK:
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
