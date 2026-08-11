"""Keeps vendored modules from corrupting each other's session state.

Three key names collide across the six dashboards (`generators`,
`supply_bids`, `demand_bids`) with different shapes. Since every experiment
shares one Streamlit session, switching from a Week 7 experiment to a Week 8 one
would hand Week 8 a Week 7 list and crash it.

Rule: when the active source module changes, drop every key the vendored code
could own. Hub-owned keys are prefixed and always survive. Switching between two
experiments of the *same* module preserves state, matching how those dashboards
behave standalone.
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
