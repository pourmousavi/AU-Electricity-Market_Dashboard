import pytest

from hub.catalogue import load_catalogue
from hub.pages_experiment import resolve_access

CATALOGUE = load_catalogue()


def _row(**overrides) -> dict:
    row = {"experiment_id": "w2.consumer_model", "title": "Consumer Model",
           "blurb": "", "enabled": True, "orphaned": False,
           "topic_id": 1, "sort_order": 0}
    row.update(overrides)
    return row


def test_enabled_experiment_is_ok() -> None:
    status, _ = resolve_access(_row(), CATALOGUE)
    assert status == "ok"


def test_missing_row_is_missing() -> None:
    status, _ = resolve_access(None, CATALOGUE)
    assert status == "missing"


def test_disabled_experiment_is_refused() -> None:
    status, message = resolve_access(_row(enabled=False), CATALOGUE)
    assert status == "disabled"
    assert message


def test_orphaned_experiment_is_refused() -> None:
    status, _ = resolve_access(_row(orphaned=True), CATALOGUE)
    assert status == "orphaned"


def test_row_without_catalogue_entry_is_orphaned() -> None:
    status, _ = resolve_access(_row(experiment_id="w9.gone"), CATALOGUE)
    assert status == "orphaned"


@pytest.mark.parametrize("status_row,expected", [
    ({"enabled": False, "orphaned": True}, "orphaned"),
    ({"enabled": False, "orphaned": False}, "disabled"),
])
def test_orphaned_takes_precedence_over_disabled(status_row, expected) -> None:
    status, _ = resolve_access(_row(**status_row), CATALOGUE)
    assert status == expected
