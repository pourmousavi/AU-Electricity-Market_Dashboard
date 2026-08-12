from pathlib import Path

from hub.catalogue import load_catalogue

ROOT = Path(__file__).resolve().parent.parent


def test_catalogue_is_the_experiments_directory() -> None:
    catalogue = load_catalogue()
    assert len(catalogue) == 25
    assert "market_equilibrium" in catalogue
    assert catalogue["market_equilibrium"].path == ROOT / "experiments" / "market_equilibrium.py"


def test_private_modules_are_not_experiments() -> None:
    catalogue = load_catalogue()
    assert not [k for k in catalogue if k.startswith("_")]
    assert "__init__" not in catalogue
