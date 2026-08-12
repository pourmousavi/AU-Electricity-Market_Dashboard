import pytest
from sqlalchemy import create_engine, func, select

from hub import analytics, db


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    return eng


def test_hash_is_stable_for_same_salt() -> None:
    assert analytics.hash_ip("1.2.3.4", "salt") == analytics.hash_ip("1.2.3.4", "salt")


def test_hash_differs_across_salts() -> None:
    assert analytics.hash_ip("1.2.3.4", "a") != analytics.hash_ip("1.2.3.4", "b")


def test_hash_differs_across_addresses() -> None:
    assert analytics.hash_ip("1.2.3.4", "s") != analytics.hash_ip("1.2.3.5", "s")


def test_hash_is_not_reversible_to_the_input() -> None:
    digest = analytics.hash_ip("203.0.113.9", "s")
    assert "203.0.113.9" not in digest
    assert len(digest) == 64


def test_extract_takes_first_address_of_forwarded_chain() -> None:
    headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1, 10.0.0.2"}
    assert analytics.extract_client_ip(headers) == "203.0.113.9"


def test_extract_is_case_insensitive() -> None:
    assert analytics.extract_client_ip({"x-forwarded-for": "203.0.113.9"}) == "203.0.113.9"


def test_extract_falls_back_to_real_ip() -> None:
    assert analytics.extract_client_ip({"X-Real-Ip": "198.51.100.7"}) == "198.51.100.7"


def test_extract_returns_none_when_absent() -> None:
    assert analytics.extract_client_ip({"User-Agent": "x"}) is None


class _FakeContext:
    """Stand-in for `st.context`: a plain object exposing a `.headers` mapping.

    Lets tests inject headers (or simulate their absence) without a live
    Streamlit runtime, mirroring how `extract_client_ip` tests pass a plain
    dict directly.
    """

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _RaisingContext:
    """Stand-in for `st.context` when no ScriptRunContext is available."""

    @property
    def headers(self):
        raise RuntimeError("no runtime")


def test_identity_label_is_unique_ips_when_forwarding_header_present(monkeypatch) -> None:
    monkeypatch.setattr(
        analytics.st, "context", _FakeContext({"X-Forwarded-For": "203.0.113.9"})
    )
    assert analytics.identity_label() == "Unique IPs"


def test_identity_label_is_unique_devices_when_header_absent(monkeypatch) -> None:
    monkeypatch.setattr(analytics.st, "context", _FakeContext({"User-Agent": "x"}))
    assert analytics.identity_label() == "Unique devices"


def test_identity_label_is_unique_devices_outside_streamlit_runtime(monkeypatch) -> None:
    monkeypatch.setattr(analytics.st, "context", _RaisingContext())
    assert analytics.identity_label() == "Unique devices"


_TEST_SALT = "test-fixture-salt-not-a-real-secret"


def _visitor_row(engine, session_id: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            select(db.visitor_session).where(db.visitor_session.c.id == session_id)
        ).first()
    assert row is not None
    return dict(row._mapping)


def _patch_streamlit_for_session(monkeypatch, *, headers: dict[str, str], query_params: dict) -> None:
    """Install fakes for every `st.*` surface `ensure_session` touches.

    `state` is passed straight into `ensure_session` (a plain dict), so this
    only needs to stand in for `st.context`, `st.query_params` and
    `st.secrets` -- no live Streamlit runtime required.
    """
    monkeypatch.setattr(analytics.st, "context", _FakeContext(headers))
    monkeypatch.setattr(analytics.st, "query_params", query_params)
    monkeypatch.setattr(analytics.st, "secrets", {"analytics": {"ip_salt": _TEST_SALT}})


def test_ensure_session_never_persists_the_raw_ip(monkeypatch, engine) -> None:
    """The regression net for the whole privacy claim.

    Would fail if `ensure_session` ever stored `ip` instead of `hash_ip(ip,
    salt)` -- for either the session id or the ip_hash column.
    """
    raw_ip = "203.0.113.9"
    _patch_streamlit_for_session(
        monkeypatch, headers={"X-Forwarded-For": raw_ip}, query_params={}
    )
    state: dict = {}

    session_id = analytics.ensure_session(engine, state=state)

    row = _visitor_row(engine, session_id)
    assert row["ip_hash"] == analytics.hash_ip(raw_ip, _TEST_SALT)
    for column, value in row.items():
        assert raw_ip not in str(value), f"raw IP leaked into column {column!r}"
    assert raw_ip not in session_id


def test_ensure_session_is_idempotent_per_state(monkeypatch, engine) -> None:
    _patch_streamlit_for_session(
        monkeypatch, headers={"X-Forwarded-For": "203.0.113.9"}, query_params={}
    )
    state: dict = {}

    first = analytics.ensure_session(engine, state=state)
    second = analytics.ensure_session(engine, state=state)

    assert first == second
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(db.visitor_session)
        ).scalar_one()
    assert count == 1


def test_ensure_session_falls_back_to_device_id_without_forwarding_header(
    monkeypatch, engine
) -> None:
    query_params: dict = {}
    _patch_streamlit_for_session(monkeypatch, headers={}, query_params=query_params)
    state: dict = {}

    session_id = analytics.ensure_session(engine, state=state)

    assert analytics.DEVICE_PARAM in query_params
    device = query_params[analytics.DEVICE_PARAM]
    row = _visitor_row(engine, session_id)
    assert row["ip_hash"] == analytics.hash_ip(device, _TEST_SALT)
    # No IP was ever extracted, so nothing IP-derived can have been stored --
    # the hash traces back to the anonymous device id, not an address.
    for column, value in row.items():
        assert "203.0.113" not in str(value)


def test_ensure_session_reuses_existing_device_id(monkeypatch, engine) -> None:
    query_params = {analytics.DEVICE_PARAM: "already-minted-device-id"}
    _patch_streamlit_for_session(monkeypatch, headers={}, query_params=query_params)
    state: dict = {}

    session_id = analytics.ensure_session(engine, state=state)

    assert query_params[analytics.DEVICE_PARAM] == "already-minted-device-id"
    row = _visitor_row(engine, session_id)
    assert row["ip_hash"] == analytics.hash_ip("already-minted-device-id", _TEST_SALT)


def test_track_buffers_without_writing(engine) -> None:
    state: dict = {}
    analytics.track(engine, "home_view", state=state, flush_at=5)
    assert len(state[analytics.BUFFER_KEY]) == 1
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.event)).scalar_one() == 0


def test_buffer_flushes_at_threshold(engine) -> None:
    state: dict = {}
    for _ in range(5):
        analytics.track(engine, "home_view", state=state, flush_at=5)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.event)).scalar_one() == 5
    assert state[analytics.BUFFER_KEY] == []


def test_explicit_flush_writes_remainder(engine) -> None:
    state: dict = {}
    analytics.track(engine, "topic_view", topic_id=3, state=state, flush_at=99)
    assert analytics.flush(engine, state=state) == 1
    with engine.connect() as conn:
        row = conn.execute(select(db.event)).first()
    assert row._mapping["kind"] == "topic_view"
    assert row._mapping["topic_id"] == 3


def test_flush_on_empty_buffer_is_a_noop(engine) -> None:
    assert analytics.flush(engine, state={}) == 0
