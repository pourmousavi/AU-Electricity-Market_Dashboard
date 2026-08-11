from pathlib import Path

import pytest

from scripts.sync_sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("filename", sorted(SOURCES))
def test_source_file_present_and_parses(filename: str) -> None:
    """Every vendored source exists and is valid Python we can parse."""
    import ast

    path = ROOT / "sources" / filename
    assert path.exists(), f"{filename} missing from sources/"
    ast.parse(path.read_text(encoding="utf-8"))


def test_sources_are_in_sync_with_upstream() -> None:
    """Vendored copies match upstream byte-for-byte."""
    from scripts.sync_sources import sync

    assert sync(dry_run=True) == []
