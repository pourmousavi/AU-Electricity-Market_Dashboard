from hub.state import ACTIVE_SOURCE_KEY, HUB_PREFIX, isolate


def test_first_call_sets_active_source_and_clears_nothing() -> None:
    state = {"generators": [1, 2]}
    assert isolate(state, "week7") is False
    assert state["generators"] == [1, 2]
    assert state[ACTIVE_SOURCE_KEY] == "week7"


def test_same_source_preserves_state() -> None:
    state = {ACTIVE_SOURCE_KEY: "week7", "generators": [1, 2]}
    assert isolate(state, "week7") is False
    assert state["generators"] == [1, 2]


def test_different_source_clears_foreign_keys() -> None:
    state = {ACTIVE_SOURCE_KEY: "week7", "generators": [1, 2], "demand_bids": []}
    assert isolate(state, "week8") is True
    assert "generators" not in state
    assert "demand_bids" not in state
    assert state[ACTIVE_SOURCE_KEY] == "week8"


def test_hub_keys_survive_a_switch() -> None:
    state = {
        ACTIVE_SOURCE_KEY: "week7",
        f"{HUB_PREFIX}events": ["a"],
        f"{HUB_PREFIX}session_id": "abc",
        "generators": [1],
    }
    isolate(state, "week8")
    assert state[f"{HUB_PREFIX}events"] == ["a"]
    assert state[f"{HUB_PREFIX}session_id"] == "abc"
    assert "generators" not in state
