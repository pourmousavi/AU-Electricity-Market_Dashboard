"""The catalogue is the experiments/ directory.

An experiment IS a module in experiments/ exposing render(); its id is the
filename stem. Everything about how an experiment is *presented* (topic,
title, order, enabled) lives in the database and is edited from the admin
panel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CatalogueError(Exception):
    """experiments/ is not usable."""


@dataclass(frozen=True)
class Experiment:
    id: str
    path: Path


def load_catalogue(directory: Path | None = None) -> dict[str, Experiment]:
    """Every experiment module, keyed by id, in alphabetical order."""
    directory = directory or ROOT / "experiments"
    if not directory.is_dir():
        raise CatalogueError(f"no experiments directory at {directory}")

    out: dict[str, Experiment] = {}
    for path in sorted(directory.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        out[path.stem] = Experiment(id=path.stem, path=path)
    return out
