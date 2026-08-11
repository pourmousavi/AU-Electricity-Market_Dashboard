"""Anonymous usage capture.

Raw IP addresses are never stored. We keep a salted SHA-256 hash, which is
enough to count unique visitors and spot repeat visits, and is not reasonably
re-identifiable without the salt (which lives only in deployment secrets).

If the platform does not forward the client IP at all, we fall back to an
anonymous id in the URL query string and count devices instead — and say so, in
the admin panel, rather than mislabelling the number. `identity_label()` is how
the admin panel finds out which of the two is actually true on this
deployment: it is derived at call time from `st.context.headers`, never
hardcoded, because whether the hosting platform forwards a client IP is a
deployment fact that can change without a code change.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Mapping, MutableMapping

import streamlit as st
from sqlalchemy import insert
from sqlalchemy.engine import Engine

from hub import db

BUFFER_KEY = "_hub.events"
SESSION_KEY = "_hub.session_id"
DEVICE_PARAM = "d"
FLUSH_AT = 5

_FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip")


def hash_ip(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def extract_client_ip(headers: Mapping[str, str]) -> str | None:
    """First address of the forwarding chain, or None."""
    lowered = {str(k).lower(): v for k, v in headers.items()}
    for name in _FORWARD_HEADERS:
        value = lowered.get(name)
        if value:
            return value.split(",")[0].strip() or None
    return None


def identity_label() -> str:
    """What the unique-visitor metric actually measures on THIS deployment.

    Never hardcode this. If the platform forwards a client IP we count unique
    IPs; if not, we count unique devices via an anonymous id in the URL. The
    admin panel shows whichever is true rather than a guess.
    """
    try:
        headers = dict(st.context.headers)
    except Exception:  # not inside a live Streamlit runtime
        return "Unique devices"
    return "Unique IPs" if extract_client_ip(headers) is not None else "Unique devices"


def _state(state: MutableMapping | None) -> MutableMapping:
    return st.session_state if state is None else state


def ensure_session(engine: Engine, state: MutableMapping | None = None) -> str:
    """Register this browser session once; return its id."""
    store = _state(state)
    existing = store.get(SESSION_KEY)
    if existing:
        return existing

    try:
        headers = dict(st.context.headers)
    except Exception:  # not inside a live Streamlit runtime
        headers = {}

    ip = extract_client_ip(headers)
    if ip is not None:
        ip_hash = hash_ip(ip, st.secrets["analytics"]["ip_salt"])
        session_id = ip_hash[:32] + "-" + secrets.token_hex(8)
    else:
        device = st.query_params.get(DEVICE_PARAM)
        if not device:
            device = secrets.token_hex(8)
            st.query_params[DEVICE_PARAM] = device
        ip_hash = hash_ip(device, st.secrets["analytics"]["ip_salt"])
        session_id = f"{device}-{secrets.token_hex(8)}"

    with engine.begin() as conn:
        conn.execute(insert(db.visitor_session).values(
            id=session_id,
            ip_hash=ip_hash,
            user_agent=headers.get("user-agent") or headers.get("User-Agent"),
            referrer=headers.get("referer") or headers.get("Referer"),
        ))

    store[SESSION_KEY] = session_id
    return session_id


def track(
    engine: Engine,
    kind: str,
    topic_id: int | None = None,
    experiment_id: str | None = None,
    dwell_ms: int | None = None,
    state: MutableMapping | None = None,
    flush_at: int = FLUSH_AT,
) -> None:
    """Buffer one event; write the batch once it is worth a round trip."""
    store = _state(state)
    buffer: list[dict[str, Any]] = store.setdefault(BUFFER_KEY, [])
    buffer.append({
        "session_id": store.get(SESSION_KEY),
        "kind": kind,
        "topic_id": topic_id,
        "experiment_id": experiment_id,
        "dwell_ms": dwell_ms,
    })
    if len(buffer) >= flush_at:
        flush(engine, state=store)


def flush(engine: Engine, state: MutableMapping | None = None) -> int:
    store = _state(state)
    buffer: list[dict[str, Any]] = store.get(BUFFER_KEY) or []
    if not buffer:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(db.event), buffer)
    written = len(buffer)
    store[BUFFER_KEY] = []
    return written


def now_ms() -> int:
    return int(time.monotonic() * 1000)
