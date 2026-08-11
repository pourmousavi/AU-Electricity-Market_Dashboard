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
