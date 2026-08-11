"""Password gate for the admin panel.

Deliberately simple: one shared password from deployment secrets, compared in
constant time, with a lockout so it cannot be ground down by guessing. There is
no student login anywhere on this site — this gate exists only to keep the
usage data and content toggles to the course coordinator.
"""
from __future__ import annotations

import hmac
import time
from typing import MutableMapping

import streamlit as st

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
ATTEMPT_DELAY_SECONDS = 1.0

AUTHED_KEY = "_hub.admin_ok"
FAILURES_KEY = "_hub.admin_failures"
LOCKED_AT_KEY = "_hub.admin_locked_at"


def password_matches(supplied: str, expected: str) -> bool:
    if not supplied or not expected:
        return False
    return hmac.compare_digest(str(supplied), str(expected))


def register_failure(state: MutableMapping, now: float) -> None:
    failures = int(state.get(FAILURES_KEY, 0)) + 1
    state[FAILURES_KEY] = failures
    if failures >= MAX_ATTEMPTS:
        state[LOCKED_AT_KEY] = now


def lockout_remaining(state: MutableMapping, now: float) -> int:
    locked_at = state.get(LOCKED_AT_KEY)
    if locked_at is None:
        return 0
    elapsed = now - float(locked_at)
    if elapsed >= LOCKOUT_SECONDS:
        state.pop(LOCKED_AT_KEY, None)
        state[FAILURES_KEY] = 0
        return 0
    return int(LOCKOUT_SECONDS - elapsed)


def clear_failures(state: MutableMapping) -> None:
    state.pop(FAILURES_KEY, None)
    state.pop(LOCKED_AT_KEY, None)


def require_admin(state: MutableMapping | None = None) -> bool:
    """Render the gate. Returns True only when authorised."""
    store = st.session_state if state is None else state
    if store.get(AUTHED_KEY):
        return True

    st.title("Course coordinator sign-in")

    remaining = lockout_remaining(store, time.monotonic())
    if remaining:
        st.error(f"Too many attempts. Try again in {remaining // 60 + 1} minute(s).")
        return False

    supplied = st.text_input("Password", type="password", key="_hub.admin_pw")
    if not st.button("Sign in", key="_hub.admin_signin"):
        return False

    time.sleep(ATTEMPT_DELAY_SECONDS)
    if password_matches(supplied, st.secrets.get("admin", {}).get("password", "")):
        clear_failures(store)
        store[AUTHED_KEY] = True
        st.rerun()

    register_failure(store, time.monotonic())
    st.error("Incorrect password.")
    return False
