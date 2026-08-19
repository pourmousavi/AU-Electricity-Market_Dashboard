"""Admin panel behaviour that a coordinator can trigger by mis-clicking.

hub.admin renders through real (but bare-mode, no live runtime) streamlit
calls, the same way tests/test_pages_experiment.py does. Widget *returns* are
what a real click would produce, so they are stubbed; everything else — the
database, the branch structure, the session-state bookkeeping — is real.
"""
import pytest
import streamlit as st
from sqlalchemy import create_engine, func, select
from streamlit.delta_generator import DeltaGenerator

from hub import admin, db
from hub.catalogue import load_catalogue

CATALOGUE = load_catalogue()


@pytest.fixture()
def engine():
    """A database in the state the coordinator would have left it in.

    seed_initial parks everything unsorted and switched off, so the fixture
    does what the admin panel does and switches the experiments on -- an
    unconfirmed delete disabling them is only observable if something was
    enabled to begin with.
    """
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    db.seed_initial(eng, CATALOGUE)
    for exp_id in CATALOGUE:
        db.set_experiment_enabled(eng, exp_id, True)
    return eng


@pytest.fixture(autouse=True)
def _clean_session_state():
    for key in admin.NEW_TOPIC_KEYS:
        st.session_state.pop(key, None)
    yield
    for key in admin.NEW_TOPIC_KEYS:
        st.session_state.pop(key, None)


class _Rerun(Exception):
    """Stands in for streamlit's RerunException, which st.rerun raises.

    It matters that this aborts the render: a real st.rerun() stops the script
    dead, so only the first matching button in the topic loop ever acts.
    """


def _render_content(engine) -> bool:
    """Render the content tab once. Returns True if it asked for a rerun."""
    try:
        admin._render_content(engine, CATALOGUE)
    except _Rerun:
        return True
    return False


def _topic_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(db.topic)).scalar_one()


def _stub_widgets(monkeypatch, *, buttons, checkbox_value=False, text_inputs=None):
    """Make every widget return what the given click state would produce.

    `buttons` maps a label prefix to the value that widget returns; anything
    unlisted returns False. Column widgets (`save.button`, `delete.checkbox`)
    are methods on DeltaGenerator, while `st.button` is a bound method
    captured at import, so both have to be stubbed.
    """
    def button(label, **kwargs):
        if kwargs.get("disabled"):
            return False
        for prefix, value in buttons.items():
            if str(label).startswith(prefix):
                return value
        return False

    def text_input(label, value="", **kwargs):
        key = kwargs.get("key", "")
        if text_inputs and key in text_inputs:
            return text_inputs[key]
        return value

    monkeypatch.setattr(st, "button", lambda label, **kw: button(label, **kw))
    monkeypatch.setattr(DeltaGenerator, "button", lambda self, label, **kw: button(label, **kw))
    monkeypatch.setattr(st, "checkbox", lambda label, **kw: checkbox_value)
    monkeypatch.setattr(DeltaGenerator, "checkbox", lambda self, label, **kw: checkbox_value)
    monkeypatch.setattr(st, "text_input", text_input)

    def rerun(*args, **kwargs):
        raise _Rerun()

    monkeypatch.setattr(st, "rerun", rerun)


def test_creating_a_topic_clears_the_form_so_a_second_click_cannot_duplicate(
    monkeypatch, engine
) -> None:
    """topic.name has no unique constraint; the form is the only guard."""
    st.session_state[admin.NEW_TOPIC_KEYS[0]] = "Week 9"
    st.session_state[admin.NEW_TOPIC_KEYS[1]] = "Extra material"
    st.session_state[admin.NEW_TOPIC_KEYS[2]] = "Opens later."

    _stub_widgets(
        monkeypatch,
        buttons={"Create topic": True},
        text_inputs={
            "_hub.newtopic_name": "Week 9",
            "_hub.newtopic_sub": "Extra material",
            "_hub.newtopic_unlock": "Opens later.",
        },
    )

    before = _topic_count(engine)
    assert _render_content(engine) is True

    assert _topic_count(engine) == before + 1
    for key in admin.NEW_TOPIC_KEYS:
        assert key not in st.session_state, f"{key} survived the rerun"


def test_installed_streamlit_supports_the_admin_panels_api() -> None:
    """The admin panel is the half of the site no smoke test exercises.

    hub.admin passes key= to st.expander and st.tabs. That parameter only
    exists from streamlit 1.55.0; on anything older the whole panel dies with
    a TypeError while the student site looks perfectly fine, so nobody notices
    until the coordinator tries to change something. requirements.txt floors
    the version at 1.55 -- this fails loudly if an environment ignores that.
    """
    import inspect

    for name in ("expander", "tabs"):
        parameters = inspect.signature(getattr(st, name)).parameters
        assert "key" in parameters, (
            f"st.{name} does not accept key= — streamlit {st.__version__} is "
            "below the 1.55 floor in requirements.txt"
        )


def test_clear_new_topic_form_is_idempotent() -> None:
    state = {"_hub.newtopic_name": "Week 9", "_hub.other": "keep me"}
    admin.clear_new_topic_form(state)
    admin.clear_new_topic_form(state)
    assert state == {"_hub.other": "keep me"}


def test_delete_topic_does_nothing_until_the_confirmation_is_ticked(
    monkeypatch, engine
) -> None:
    """delete_topic is unrecoverable: it drops the topic's text and disables
    every experiment in it. One stray click next to Save must not do that."""
    _stub_widgets(monkeypatch, buttons={"⚠️ Delete topic": True}, checkbox_value=False)

    before = _topic_count(engine)
    assert _render_content(engine) is False

    assert _topic_count(engine) == before, "delete fired without confirmation"
    enabled = [
        r for r in db.list_experiments(engine, topic_id=None, include_disabled=True)
        if r["enabled"]
    ]
    assert enabled, "experiments were disabled by an unconfirmed delete"


def test_delete_topic_proceeds_once_the_confirmation_is_ticked(
    monkeypatch, engine
) -> None:
    _stub_widgets(monkeypatch, buttons={"⚠️ Delete topic": True}, checkbox_value=True)

    before = _topic_count(engine)
    assert _render_content(engine) is True

    assert _topic_count(engine) == before - 1


@pytest.mark.parametrize(
    "topic_id, orphaned, expected",
    [
        (1, False, "Pool Pricing · pool_pricing :blue-badge[Topic 3]"),
        (None, False, "Pool Pricing · pool_pricing :grey-badge[unassigned]"),
        # A topic that was deleted out from under the experiment reads the
        # same as never having been assigned -- both mean no student sees it.
        (99, False, "Pool Pricing · pool_pricing :grey-badge[unassigned]"),
        (1, True, "Pool Pricing · pool_pricing :blue-badge[Topic 3] ⚠️ orphaned"),
    ],
)
def test_experiment_label_badges_the_topic(topic_id, orphaned, expected):
    choices = {None: "— unassigned —", 1: " Topic 3"}
    row = {
        "experiment_id": "pool_pricing", "title": "Pool Pricing",
        "topic_id": topic_id, "orphaned": orphaned,
    }
    assert admin.experiment_label(row, choices) == expected


def test_experiment_label_neutralises_brackets_in_a_topic_name():
    """Badge syntax is bracket-delimited; a stray ] would truncate the badge."""
    row = {
        "experiment_id": "x", "title": "X", "topic_id": 1, "orphaned": False,
    }
    label = admin.experiment_label(row, {None: "—", 1: "Topic [3]"})
    assert label == "X · x :blue-badge[Topic (3)]"
