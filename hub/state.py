"""Keeps independent experiment modules from corrupting each other's state.

Every experiment shares one Streamlit session, and session-state keys can
collide between independent experiment modules -- `generators`, `supply_bids`
and `demand_bids` mean different things with different shapes depending on
which experiment set them. Moving from one experiment to an unrelated one
must not hand it a foreign value under a key it also happens to use, or it
will crash or silently misbehave.

Rule: when the active STATE_GROUP changes, drop every non-hub-owned key.
Hub-owned keys are prefixed and always survive. Modules that share a common
`experiments/_kit` page declare the same STATE_GROUP, so switching between
them preserves state -- a student moving between sibling experiments keeps
their inputs, matching how a single tabbed dashboard used to behave.
"""
from __future__ import annotations

from typing import MutableMapping

HUB_PREFIX = "_hub."
ACTIVE_SOURCE_KEY = f"{HUB_PREFIX}active_source"


def isolate(session_state: MutableMapping, source_key: str) -> bool:
    """Clear foreign module state if the active source changed.

    Returns True if keys were cleared.
    """
    previous = session_state.get(ACTIVE_SOURCE_KEY)
    cleared = False

    if previous is not None and previous != source_key:
        foreign = [k for k in list(session_state) if not str(k).startswith(HUB_PREFIX)]
        for key in foreign:
            del session_state[key]
        cleared = True

    session_state[ACTIVE_SOURCE_KEY] = source_key
    return cleared
