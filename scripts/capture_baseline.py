"""Record what every experiment renders TODAY, before the split.

Run once, from the repo root, while the old runner/catalogue still exist:

    .venv/bin/python scripts/capture_baseline.py

The output is committed and used by tests/test_extraction_faithful.py to prove
each extracted module renders the same thing as the bundle it came from.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Running this file directly (not via `python -m` or pytest's pythonpath=.)
# puts scripts/ rather than the repo root on sys.path, so the repo-root
# imports below need the root added first.
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from hub.catalogue import load_catalogue

OUT = ROOT / "tests" / "baseline_render.json"

# The element collections AppTest exposes that carry rendered content. Text is
# recorded for the ones that have a string value; the rest are counted only.
TEXT_KINDS = ("title", "header", "subheader", "markdown", "info", "warning",
              "error", "success", "caption", "code", "text")
COUNT_KINDS = TEXT_KINDS + ("dataframe", "table", "metric", "button", "checkbox",
                            "selectbox", "slider", "multiselect", "radio",
                            "number_input", "text_input", "toggle", "tabs",
                            "columns", "expander")


def _harness(exp_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from hub.catalogue import load_catalogue\n"
        "from hub.runner import render_experiment\n"
        f"render_experiment(load_catalogue()[{exp_id!r}])\n"
    )


def observe(app) -> dict:
    counts, text = {}, []
    for kind in COUNT_KINDS:
        try:
            collection = getattr(app, kind)
        except (AttributeError, KeyError):
            continue
        counts[kind] = len(collection)
        if kind in TEXT_KINDS:
            for element in collection:
                value = getattr(element, "value", None)
                if isinstance(value, str):
                    text.append(value)
    return {"counts": counts, "text": text}


def main() -> None:
    catalogue = load_catalogue()
    baseline = {}
    for exp_id in sorted(catalogue):
        app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
        if app.exception:
            raise SystemExit(
                f"{exp_id} raised while capturing baseline: "
                + "; ".join(e.message for e in app.exception)
            )
        baseline[exp_id] = observe(app)
        print(f"  captured {exp_id}: {baseline[exp_id]['counts'].get('markdown', 0)} markdown")
    OUT.write_text(json.dumps(baseline, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT} for {len(baseline)} experiments")


if __name__ == "__main__":
    main()
