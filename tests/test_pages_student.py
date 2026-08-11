from hub.pages_student import topic_status


def _exp(enabled: bool = True, orphaned: bool = False) -> dict:
    return {"experiment_id": "x", "title": "X", "blurb": "",
            "enabled": enabled, "orphaned": orphaned, "sort_order": 0}


def test_topic_with_enabled_experiments_is_open() -> None:
    is_open, chip = topic_status({"enabled": True}, [_exp()])
    assert is_open is True
    assert "1" in chip


def test_disabled_topic_is_locked_even_with_enabled_experiments() -> None:
    is_open, _ = topic_status({"enabled": False}, [_exp()])
    assert is_open is False


def test_topic_with_no_enabled_experiments_is_locked() -> None:
    is_open, _ = topic_status({"enabled": True}, [_exp(enabled=False)])
    assert is_open is False


def test_orphaned_experiments_do_not_count_towards_open() -> None:
    is_open, _ = topic_status({"enabled": True}, [_exp(orphaned=True)])
    assert is_open is False


def test_empty_topic_is_locked() -> None:
    is_open, _ = topic_status({"enabled": True}, [])
    assert is_open is False


def test_chip_counts_only_available_experiments() -> None:
    _, chip = topic_status({"enabled": True}, [_exp(), _exp(), _exp(enabled=False)])
    assert "2" in chip
