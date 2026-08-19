from pathlib import Path

from streamlit.testing.v1 import AppTest

from hub import admin_auth


def test_correct_password_matches() -> None:
    assert admin_auth.password_matches("hunter2", "hunter2") is True


def test_wrong_password_does_not_match() -> None:
    assert admin_auth.password_matches("hunter3", "hunter2") is False


def test_empty_password_never_matches_empty_expected() -> None:
    """A blank configured password must not become a skeleton key."""
    assert admin_auth.password_matches("", "") is False


def test_no_lockout_before_threshold() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS - 1):
        admin_auth.register_failure(state, now=100.0 + i)
    assert admin_auth.lockout_remaining(state, now=200.0) == 0


def test_lockout_engages_at_threshold() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    remaining = admin_auth.lockout_remaining(state, now=104.0)
    assert remaining > 0


def test_lockout_expires_after_the_window() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    later = 104.0 + admin_auth.LOCKOUT_SECONDS + 1
    assert admin_auth.lockout_remaining(state, now=later) == 0


def test_clear_failures_resets_lockout() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    admin_auth.clear_failures(state)
    assert admin_auth.lockout_remaining(state, now=105.0) == 0


# --- The gate, driven the way a coordinator drives it ----------------------
#
# The helpers above are pure and easy; the failure that actually locked the
# coordinator out was in the wiring -- the typed password not reaching the
# server with the click. Only a real run through streamlit's widget plumbing
# can catch that, so these two go through AppTest.

ROOT = Path(__file__).resolve().parent.parent

GATE = (
    "import sys\n"
    f"sys.path.insert(0, {str(ROOT)!r})\n"
    "import streamlit as st\n"
    "from hub import admin_auth\n"
    "st.write('AUTHED' if admin_auth.require_admin() else 'LOCKED')\n"
)


def _gate() -> AppTest:
    app = AppTest.from_string(GATE, default_timeout=30)
    app.secrets["admin"] = {"password": "hunter2"}
    return app


def test_typed_password_reaches_the_check_with_the_submit() -> None:
    """Type, then submit: the value typed must be the value checked."""
    app = _gate().run()
    app.text_input[0].input("hunter2").run()
    app.button[0].click().run()
    assert not app.exception
    assert "AUTHED" in [m.value for m in app.markdown]


def test_submitting_an_empty_box_does_not_spend_an_attempt() -> None:
    """Autofill and stray clicks arrive empty; they must not burn the lockout."""
    app = _gate().run()
    app.button[0].click().run()
    assert "LOCKED" in [m.value for m in app.markdown]
    assert admin_auth.FAILURES_KEY not in app.session_state
