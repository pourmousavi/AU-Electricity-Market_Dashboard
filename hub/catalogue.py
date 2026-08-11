"""Loads catalogue.yaml — the repo-owned half of the configuration.

This file answers only "how do I render this experiment". Everything about how
an experiment is *presented* (topic, title, order, enabled) lives in the
database and is edited from the admin panel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VALID_MODES = {"pin_selectbox", "pin_tab"}
VALID_ENTRIES = {"module", "main"}


class CatalogueError(Exception):
    """catalogue.yaml is malformed."""


@dataclass(frozen=True)
class Experiment:
    id: str
    source_key: str
    source_path: Path
    mode: str
    selector: str
    entry: str


def load_catalogue(path: Path | None = None) -> dict[str, Experiment]:
    """Parse and validate the catalogue. Keys preserve file order."""
    path = path or ROOT / "catalogue.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = raw.get("sources") or {}
    out: dict[str, Experiment] = {}

    for entry in raw.get("experiments") or []:
        exp_id = entry.get("id")
        if not exp_id:
            raise CatalogueError(f"experiment without an id: {entry!r}")
        if exp_id in out:
            raise CatalogueError(f"duplicate experiment id: {exp_id}")

        source_key = entry.get("source")
        if source_key not in sources:
            raise CatalogueError(f"{exp_id}: unknown source {source_key!r}")

        mode = entry.get("mode")
        if mode not in VALID_MODES:
            raise CatalogueError(
                f"{exp_id}: unknown mode {mode!r} (expected one of {sorted(VALID_MODES)})"
            )

        entry_point = entry.get("entry", "module")
        if entry_point not in VALID_ENTRIES:
            raise CatalogueError(f"{exp_id}: unknown entry {entry_point!r}")

        selector = entry.get("selector")
        if not selector:
            raise CatalogueError(f"{exp_id}: selector is required")

        out[exp_id] = Experiment(
            id=exp_id,
            source_key=source_key,
            source_path=ROOT / sources[source_key],
            mode=mode,
            selector=selector,
            entry=entry_point,
        )

    return out
