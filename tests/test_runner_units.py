"""Unit tests for the runner's patching primitives.

Full end-to-end rendering of all 25 experiments is Task 7.
"""
import contextlib
import threading

import pytest
import streamlit as st

from hub import runner
from hub.catalogue import load_catalogue
from hub.runner import ExperimentRenderError, _no_page_config, _pinned_selectbox, _pinned_tabs, prepare


@pytest.fixture(autouse=True)
def _restore_patched_streamlit_attributes():
    """A leaked shim would poison every later test; undo one if it happens.

    This is a safety net, not the assertion — the tests below assert that the
    runner restores these itself.
    """
    genuine_tabs = st.tabs
    genuine_config = st.set_page_config
    had_sidebar_override = "selectbox" in st.sidebar.__dict__
    yield
    st.tabs = genuine_tabs
    st.set_page_config = genuine_config
    if not had_sidebar_override:
        st.sidebar.__dict__.pop("selectbox", None)


def test_page_config_is_noop_inside_context_and_restored_after() -> None:
    original = st.set_page_config
    with _no_page_config():
        assert st.set_page_config is not original
        st.set_page_config(page_title="ignored")  # must not raise
    assert st.set_page_config is original


def test_pinned_selectbox_returns_selector_on_first_call_only() -> None:
    original = st.sidebar.selectbox
    calls = []
    with _pinned_selectbox("Supplier Model"):
        first = st.sidebar.selectbox("Pick", ["Consumer Model", "Supplier Model"])
        calls.append(first)
    assert calls == ["Supplier Model"]
    # Bound methods are created fresh on each attribute access, so `is` would
    # compare two distinct-but-equal wrappers. `==` compares __func__/__self__,
    # which is the real question: was the genuine selectbox restored?
    assert st.sidebar.selectbox == original


def test_pinned_selectbox_rejects_absent_option() -> None:
    with pytest.raises(ExperimentRenderError, match="not among the options"):
        with _pinned_selectbox("Nonexistent"):
            st.sidebar.selectbox("Pick", ["Consumer Model"])


def test_pinned_tabs_returns_nullcontext_for_unselected() -> None:
    with _pinned_tabs(1, "Beta"):
        tabs = st.tabs(["Alpha", "Beta", "Gamma"])
    assert len(tabs) == 3
    assert isinstance(tabs[0], contextlib.nullcontext)
    assert isinstance(tabs[2], contextlib.nullcontext)
    assert not isinstance(tabs[1], contextlib.nullcontext)


def test_prepare_returns_index_for_pin_tab() -> None:
    exp = load_catalogue()["w7.pareto"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == 4


def test_prepare_returns_minus_one_for_pin_selectbox() -> None:
    exp = load_catalogue()["w2.supplier_model"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == -1


# --- Thread safety ------------------------------------------------------
#
# Streamlit runs one thread per browser session against a single process-wide
# `streamlit` module, with no global script lock. The shims below patch that
# shared module, so two students rendering two experiments at the same time
# interleave. The window is the whole exec() of a vendored dashboard --
# seconds, for the PyPSA and cvxpy solves -- so overlap in a tutorial is not a
# rare race, it is the normal case.

CATALOGUE = load_catalogue()
_DUMMY_CODE = compile("pass", "<test>", "exec")


def _run_interleaved(monkeypatch, exp_a, index_a, exp_b, index_b) -> list:
    """Force the A-enter, B-enter, A-exit, B-exit interleave with two threads.

    The waits are bounded rather than strict handshakes: once render_experiment
    serialises correctly, B *cannot* enter while A is inside, so a strict
    handshake would deadlock the fixed code instead of passing.
    """
    indices = {"A": index_a, "B": index_b}

    def fake_prepare(source_path, mode, selector):
        return _DUMMY_CODE, indices[threading.current_thread().name]

    a_entered = threading.Event()
    b_entered = threading.Event()
    a_exited = threading.Event()

    def fake_exec(code, globs):
        """Stands in for exec()ing a vendored dashboard: just holds the shims."""
        if threading.current_thread().name == "A":
            a_entered.set()
            b_entered.wait(timeout=0.5)
        else:
            b_entered.set()
            a_exited.wait(timeout=0.5)

    monkeypatch.setattr(runner, "prepare", fake_prepare)
    monkeypatch.setitem(runner.__dict__, "exec", fake_exec)

    failures: list = []

    def worker(exp, done):
        try:
            runner.render_experiment(exp)
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            failures.append(exc)
        finally:
            if done is not None:
                done.set()

    thread_a = threading.Thread(target=worker, args=(exp_a, a_exited), name="A")
    thread_b = threading.Thread(target=worker, args=(exp_b, None), name="B")

    thread_a.start()
    assert a_entered.wait(timeout=5), "session A never entered the patched block"
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive() and not thread_b.is_alive(), "render deadlocked"
    return failures


@pytest.mark.parametrize("id_a,id_b", [
    ("w6.strong_duality", "w6.weak_duality"),        # pin_tab  vs pin_tab
    ("w2.consumer_model", "w2.supplier_model"),      # selectbox vs selectbox
    ("w6.strong_duality", "w2.consumer_model"),      # pin_tab  vs selectbox
])
def test_concurrent_sessions_never_leave_a_shim_behind(monkeypatch, id_a, id_b) -> None:
    """Two overlapping renders must not corrupt the process.

    Without a lock, B captures A's *shim* as its "original" and reinstalls it
    on exit, permanently. Every later session in the process then gets the
    previous experiment's shim.
    """
    genuine_tabs = st.tabs
    genuine_config = st.set_page_config
    genuine_selectbox = st.sidebar.selectbox

    failures = _run_interleaved(
        monkeypatch, CATALOGUE[id_a], 4, CATALOGUE[id_b], 0
    )

    assert failures == [], f"a render raised: {failures}"
    assert st.tabs is genuine_tabs, "st.tabs was left patched"
    assert st.set_page_config is genuine_config, "st.set_page_config was left patched"
    # Bound methods are made fresh on each attribute access, so `is` compares
    # two distinct-but-equal wrappers; `==` asks the real question.
    assert st.sidebar.selectbox == genuine_selectbox, "st.sidebar.selectbox was left patched"


def test_admin_tabs_still_work_after_concurrent_experiment_renders(monkeypatch) -> None:
    """The concrete casualty: a leaked pin_tab shim kills the admin panel.

    hub.admin calls st.tabs with three labels. A leaked shim closed over
    index=4 (w7.pareto's tab) indexes out of range on that list and takes the
    coordinator's whole panel down until the process restarts.
    """
    _run_interleaved(
        monkeypatch,
        CATALOGUE["w6.strong_duality"], 4,
        CATALOGUE["w6.weak_duality"], 0,
    )

    tabs = st.tabs(["Usage", "Content", "Export"])
    assert len(tabs) == 3
    assert not any(isinstance(t, contextlib.nullcontext) for t in tabs)


def test_pinned_tabs_gives_other_threads_the_genuine_tabs() -> None:
    """A concurrent session inside the lock window must not see this shim."""
    seen: dict = {}

    def other_session() -> None:
        seen["tabs"] = st.tabs(["One", "Two", "Three"])

    with _pinned_tabs(1, "Beta"):
        thread = threading.Thread(target=other_session)
        thread.start()
        thread.join(timeout=5)
        owner_tabs = st.tabs(["Alpha", "Beta", "Gamma"])

    assert len(seen["tabs"]) == 3
    assert not any(isinstance(t, contextlib.nullcontext) for t in seen["tabs"])
    assert isinstance(owner_tabs[0], contextlib.nullcontext)


def test_pinned_selectbox_gives_other_threads_the_genuine_selectbox() -> None:
    seen: dict = {}

    def other_session() -> None:
        seen["value"] = st.sidebar.selectbox(
            "Pick", ["Consumer Model", "Supplier Model"]
        )

    with _pinned_selectbox("Supplier Model"):
        thread = threading.Thread(target=other_session)
        thread.start()
        thread.join(timeout=5)
        owner_value = st.sidebar.selectbox(
            "Pick", ["Consumer Model", "Supplier Model"]
        )

    assert owner_value == "Supplier Model"
    # The other thread must not be pinned to A's experiment, and must not have
    # consumed A's one-shot interception either.
    assert seen["value"] != "Supplier Model"


def test_no_page_config_does_not_swallow_another_threads_call(monkeypatch) -> None:
    """Silently dropping a concurrent set_page_config loses layout='wide'."""
    calls: list = []
    monkeypatch.setattr(st, "set_page_config", lambda **kwargs: calls.append(kwargs))

    def other_session() -> None:
        st.set_page_config(page_title="other session")

    with _no_page_config():
        st.set_page_config(page_title="vendored module")  # must be swallowed
        thread = threading.Thread(target=other_session)
        thread.start()
        thread.join(timeout=5)

    assert [c["page_title"] for c in calls] == ["other session"]
