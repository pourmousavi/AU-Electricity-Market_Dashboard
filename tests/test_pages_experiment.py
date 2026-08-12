import logging
from unittest.mock import Mock

import pytest
import streamlit as st
from sqlalchemy import create_engine, select

from hub import analytics, db, pages_experiment
from hub.catalogue import load_catalogue
from hub.pages_experiment import resolve_access
from hub.runner import ExperimentRenderError

CATALOGUE = load_catalogue()


def _row(**overrides) -> dict:
    row = {"experiment_id": "w2.consumer_model", "title": "Consumer Model",
           "blurb": "", "enabled": True, "orphaned": False,
           "topic_id": 1, "sort_order": 0}
    row.update(overrides)
    return row


def test_enabled_experiment_is_ok() -> None:
    status, _ = resolve_access(_row(), CATALOGUE)
    assert status == "ok"


def test_missing_row_is_missing() -> None:
    status, _ = resolve_access(None, CATALOGUE)
    assert status == "missing"


def test_disabled_experiment_is_refused() -> None:
    status, message = resolve_access(_row(enabled=False), CATALOGUE)
    assert status == "disabled"
    assert message


def test_orphaned_experiment_is_refused() -> None:
    status, _ = resolve_access(_row(orphaned=True), CATALOGUE)
    assert status == "orphaned"


def test_row_without_catalogue_entry_is_orphaned() -> None:
    status, _ = resolve_access(_row(experiment_id="w9.gone"), CATALOGUE)
    assert status == "orphaned"


@pytest.mark.parametrize("status_row,expected", [
    ({"enabled": False, "orphaned": True}, "orphaned"),
    ({"enabled": False, "orphaned": False}, "disabled"),
])
def test_orphaned_takes_precedence_over_disabled(status_row, expected) -> None:
    status, _ = resolve_access(_row(**status_row), CATALOGUE)
    assert status == expected


# --- Fix round 1 --------------------------------------------------------
#
# hub.pages_experiment renders through real (but bare-mode, no live runtime)
# streamlit calls: st.session_state behaves as an in-process dict, st.markdown
# / st.button / st.error no-op safely (see streamlit's own "missing
# ScriptRunContext... running in bare mode" warning). That is enough to
# exercise render_experiment_page / close_previous end to end against an
# in-memory SQLite engine, without needing `streamlit run`.


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    db.seed_initial(eng, CATALOGUE)
    return eng


@pytest.fixture(autouse=True)
def _clean_session_state():
    """hub keys are process-global in bare-mode st.session_state; isolate tests."""
    for key in (
        pages_experiment.OPEN_EXP_KEY,
        pages_experiment.OPEN_TS_KEY,
        analytics.BUFFER_KEY,
        analytics.SESSION_KEY,
    ):
        st.session_state.pop(key, None)
    yield
    for key in (
        pages_experiment.OPEN_EXP_KEY,
        pages_experiment.OPEN_TS_KEY,
        analytics.BUFFER_KEY,
        analytics.SESSION_KEY,
    ):
        st.session_state.pop(key, None)


def test_render_error_does_not_call_st_exception_and_reports_instead(
    monkeypatch, engine, caplog
) -> None:
    """Finding 1: students must never see a traceback.

    The failure must instead land as a server-side log record and an
    `experiment_error` analytics event the coordinator can see in the admin
    panel -- not as `st.exception(exc)` on the public page.
    """
    experiment_id = "w2.consumer_model"
    st.session_state[analytics.SESSION_KEY] = "test-session"

    def _boom(_exp) -> None:
        raise ExperimentRenderError("synthetic failure for the test")

    monkeypatch.setattr(pages_experiment, "render_experiment", _boom)
    exception_spy = Mock()
    monkeypatch.setattr(pages_experiment.st, "exception", exception_spy)

    with caplog.at_level(logging.ERROR, logger="hub.pages_experiment"):
        pages_experiment.render_experiment_page(engine, experiment_id, CATALOGUE)

    assert exception_spy.called is False, "st.exception must never render on this public page"

    error_records = [r for r in caplog.records if r.name == "hub.pages_experiment"]
    assert any(experiment_id in r.getMessage() and r.exc_info for r in error_records), (
        "the failure must be logged server-side with exception info"
    )

    analytics.flush(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(db.event).where(db.event.c.kind == "experiment_error")
        ).all()
    assert len(rows) == 1
    assert rows[0]._mapping["experiment_id"] == experiment_id


def test_close_previous_with_no_current_experiment_flushes_and_clears(engine) -> None:
    """Finding 2 (unit-level): close_previous(engine, None) is what app.py's
    admin branch must call before its early return.

    Exercising the app.py wiring itself (routing to ?admin=1 clears the open
    experiment) is verified by reading app.py, not by a test here: `main()`
    needs a live query-string/secrets/session context that isn't practical to
    fake at this layer. This test instead pins down the behaviour app.py
    relies on: calling close_previous with current_experiment_id=None, as the
    admin route now does, closes out whatever experiment was open and emits
    exactly one experiment_close event -- so an admin-panel visit can never
    silently be absorbed into an experiment's dwell time.
    """
    previous_id = "w2.consumer_model"
    st.session_state[pages_experiment.OPEN_EXP_KEY] = previous_id
    st.session_state[pages_experiment.OPEN_TS_KEY] = analytics.now_ms() - 1234
    st.session_state[analytics.SESSION_KEY] = "test-session"

    pages_experiment.close_previous(engine, None)

    assert pages_experiment.OPEN_EXP_KEY not in st.session_state
    assert pages_experiment.OPEN_TS_KEY not in st.session_state

    with engine.connect() as conn:
        rows = conn.execute(
            select(db.event).where(db.event.c.kind == "experiment_close")
        ).all()
    assert len(rows) == 1
    assert rows[0]._mapping["experiment_id"] == previous_id
    assert rows[0]._mapping["dwell_ms"] is not None and rows[0]._mapping["dwell_ms"] >= 0
