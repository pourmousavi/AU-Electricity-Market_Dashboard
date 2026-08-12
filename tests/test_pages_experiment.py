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
    row = {"experiment_id": "consumer_model", "title": "Consumer Model",
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
    status, _ = resolve_access(_row(experiment_id="gone"), CATALOGUE)
    assert status == "orphaned"


@pytest.mark.parametrize("status_row,expected", [
    ({"enabled": False, "orphaned": True}, "orphaned"),
    ({"enabled": False, "orphaned": False}, "disabled"),
])
def test_orphaned_takes_precedence_over_disabled(status_row, expected) -> None:
    status, _ = resolve_access(_row(**status_row), CATALOGUE)
    assert status == expected


def _topic(**overrides) -> dict:
    row = {"id": 1, "name": "Week 2", "subtitle": "", "unlock_message": "",
           "sort_order": 0, "enabled": True}
    row.update(overrides)
    return row


def test_enabled_experiment_in_disabled_topic_is_refused() -> None:
    """A bookmarked ?view=experiment URL must not walk past a closed week.

    topic.enabled is a hard gate in pages_student.topic_status, so the whole
    week reads as locked in the UI. Every experiment is also a shareable URL,
    so those links are already in circulation.
    """
    status, message = resolve_access(
        _row(), CATALOGUE, _topic(enabled=False, unlock_message="Opens in week 2.")
    )
    assert status == "disabled"
    assert message == "Opens in week 2."


def test_disabled_topic_without_unlock_message_falls_back() -> None:
    status, message = resolve_access(
        _row(), CATALOGUE, _topic(enabled=False, unlock_message="")
    )
    assert status == "disabled"
    assert message == pages_experiment.DISABLED_MESSAGE


def test_enabled_topic_leaves_an_enabled_experiment_open() -> None:
    status, _ = resolve_access(_row(), CATALOGUE, _topic(enabled=True))
    assert status == "ok"


def test_unassigned_experiment_is_unaffected_by_the_topic_gate() -> None:
    """topic_id is nullable; no parent topic means no parent gate."""
    status, _ = resolve_access(_row(topic_id=None), CATALOGUE, None)
    assert status == "ok"


@pytest.mark.parametrize("row_overrides,expected", [
    ({"orphaned": True}, "orphaned"),
    ({"enabled": False}, "disabled"),
])
def test_topic_gate_does_not_disturb_the_existing_check_order(
    row_overrides, expected
) -> None:
    status, _ = resolve_access(
        _row(**row_overrides), CATALOGUE, _topic(enabled=False)
    )
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
    """A database in the state the coordinator would have left it in.

    seed_initial parks everything unsorted and switched off, so these tests
    do what the admin panel does: put the experiment in a live topic and turn
    it on. Without that every case below would be refused before reaching the
    behaviour under test.
    """
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    db.seed_initial(eng, CATALOGUE)
    topic_id = db.upsert_topic(eng, None, "Week 2", "", "", 0, True)
    for exp_id in CATALOGUE:
        db.assign_experiment(eng, exp_id, topic_id, 0)
        db.set_experiment_enabled(eng, exp_id, True)
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
    experiment_id = "consumer_model"
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


def test_direct_url_to_enabled_experiment_in_disabled_topic_does_not_render(
    monkeypatch, engine
) -> None:
    """Whole-week switch-off must close the experiment's own URL too.

    The coordinator sees the week locked everywhere in the UI; a student with
    a bookmarked ?view=experiment&exp=... link must not still get the full
    experiment. The experiment row itself stays enabled -- that is the point.
    """
    experiment_id = "consumer_model"
    row = db.get_experiment(engine, experiment_id)
    assert row["enabled"] and row["topic_id"] is not None

    topic = {t["id"]: t for t in db.list_topics(engine, include_disabled=True)}[
        row["topic_id"]
    ]
    db.upsert_topic(
        engine, topic["id"], topic["name"], topic["subtitle"],
        "Week 2 opens after the lecture.", topic["sort_order"], False,
    )

    assert resolve_access(
        db.get_experiment(engine, experiment_id), CATALOGUE,
        {t["id"]: t for t in db.list_topics(engine, include_disabled=True)}[
            row["topic_id"]
        ],
    ) == ("disabled", "Week 2 opens after the lecture.")

    render_spy = Mock()
    monkeypatch.setattr(pages_experiment, "render_experiment", render_spy)
    pages_experiment.render_experiment_page(engine, experiment_id, CATALOGUE)

    assert render_spy.called is False, (
        "a disabled topic must stop the vendored code from executing at all"
    )
    assert pages_experiment.OPEN_EXP_KEY not in st.session_state


def test_generic_vendored_exception_is_caught_logged_and_tracked(
    monkeypatch, engine, caplog
) -> None:
    """Vendored dashboards raise their own errors, not ExperimentRenderError.

    A cvxpy solver failure or a numpy error from an out-of-range slider is a
    plain ValueError. Before this fix it propagated to Streamlit and, with
    client.showErrorDetails at its default, rendered the traceback and the
    absolute deployment path on a public page.
    """
    experiment_id = "consumer_model"
    st.session_state[analytics.SESSION_KEY] = "test-session"

    def _boom(_exp) -> None:
        raise ValueError("solver did not converge")

    monkeypatch.setattr(pages_experiment, "render_experiment", _boom)
    error_spy = Mock()
    exception_spy = Mock()
    monkeypatch.setattr(pages_experiment.st, "error", error_spy)
    monkeypatch.setattr(pages_experiment.st, "exception", exception_spy)

    with caplog.at_level(logging.ERROR, logger="hub.pages_experiment"):
        pages_experiment.render_experiment_page(engine, experiment_id, CATALOGUE)

    assert exception_spy.called is False
    assert error_spy.called is True, "the student must get the friendly message"
    assert "reported automatically" in error_spy.call_args.args[0]

    assert any(
        r.name == "hub.pages_experiment" and r.exc_info for r in caplog.records
    ), "the failure must be logged server-side with exception info"

    analytics.flush(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(db.event).where(db.event.c.kind == "experiment_error")
        ).all()
    assert len(rows) == 1
    assert rows[0]._mapping["experiment_id"] == experiment_id


def test_client_error_details_are_suppressed_in_deployed_config() -> None:
    """The backstop for anything raised outside the try block above.

    Streamlit defaults client.showErrorDetails to "full", which would put the
    exception, the absolute deployment path and a source excerpt on a public
    page with no login.
    """
    import tomllib
    from pathlib import Path

    config = tomllib.loads(
        (Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml")
        .read_text(encoding="utf-8")
    )
    assert config["client"]["showErrorDetails"] == "none"


def test_keyboard_interrupt_is_not_swallowed(monkeypatch, engine) -> None:
    """`except Exception` must stay narrower than BaseException."""
    def _interrupt(_exp) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(pages_experiment, "render_experiment", _interrupt)
    st.session_state[analytics.SESSION_KEY] = "test-session"

    with pytest.raises(KeyboardInterrupt):
        pages_experiment.render_experiment_page(
            engine, "consumer_model", CATALOGUE
        )


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
    previous_id = "consumer_model"
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
