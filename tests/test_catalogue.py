from pathlib import Path

import pytest

from hub.catalogue import CatalogueError, Experiment, load_catalogue

ROOT = Path(__file__).resolve().parent.parent


def test_loads_all_twenty_five_experiments() -> None:
    cat = load_catalogue()
    assert len(cat) == 25
    assert all(isinstance(e, Experiment) for e in cat.values())


def test_source_paths_exist() -> None:
    for exp in load_catalogue().values():
        assert exp.source_path.exists(), f"{exp.id} points at a missing file"


def test_entry_defaults_to_module() -> None:
    assert load_catalogue()["w2.consumer_model"].entry == "module"


def test_pin_tab_entries_carry_entry_point() -> None:
    cat = load_catalogue()
    assert cat["w7.pareto"].entry == "main"
    assert cat["w6.strong_duality"].entry == "module"


def test_rejects_unknown_mode(tmp_path: Path) -> None:
    bad = tmp_path / "c.yaml"
    bad.write_text(
        "sources: {week2: sources/week2_consumer_supplier.py}\n"
        "experiments:\n"
        "  - {id: x, source: week2, mode: teleport, selector: 'y'}\n"
    )
    with pytest.raises(CatalogueError, match="unknown mode"):
        load_catalogue(bad)


def test_rejects_unknown_source(tmp_path: Path) -> None:
    bad = tmp_path / "c.yaml"
    bad.write_text(
        "sources: {week2: sources/week2_consumer_supplier.py}\n"
        "experiments:\n"
        "  - {id: x, source: week9, mode: pin_selectbox, selector: 'y'}\n"
    )
    with pytest.raises(CatalogueError, match="unknown source"):
        load_catalogue(bad)


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    bad = tmp_path / "c.yaml"
    bad.write_text(
        "sources: {week2: sources/week2_consumer_supplier.py}\n"
        "experiments:\n"
        "  - {id: x, source: week2, mode: pin_selectbox, selector: 'a'}\n"
        "  - {id: x, source: week2, mode: pin_selectbox, selector: 'b'}\n"
    )
    with pytest.raises(CatalogueError, match="duplicate"):
        load_catalogue(bad)
