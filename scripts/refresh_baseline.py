"""Re-record what every experiment renders, after an intended content change.

`tests/baseline_render.json` started life as the record of what the six
bundled dashboards rendered before they were split into `experiments/`, and
`tests/test_extraction_faithful.py` pins every experiment against it. That is
what proved the split was faithful.

It also means the record is now a snapshot test. The moment you deliberately
reword an `st.markdown` in an experiment, that test fails — correctly, because
what students see changed. This script is how you say "yes, I meant that":

    .venv/bin/python scripts/refresh_baseline.py --check   # what would change
    .venv/bin/python scripts/refresh_baseline.py           # accept it

Refreshing REPLACES the pre-split record with current behaviour. The original
is not lost -- it is in git history -- but after the first refresh the file no
longer proves anything about the split, only about the last accepted state.
Read the diff before you commit it: every line it changes is a line a student
would have seen change.

Expect the FIRST refresh to show 11 experiments changing — the weeks 2, 3 and
4 ones, dropping the eight sidebar-branding lines each ("⚡ Electricity Market
Dashboard", the course code, the version, four dividers). Those are what the
split deliberately left behind and what the allowance in
`tests/test_extraction_faithful.py` currently permits; a refresh simply bakes
that in. Anything ELSE in that first diff is a real change worth reading.

Rendering goes through `hub.runner.render_experiment`, the same path the hub
itself uses, so session-state isolation and STATE_GROUP behave as in the app.
Keys stay the pre-split ids (`w2.market_equilibrium`) because that is what
`tests/test_extraction_faithful.py` maps to; the mapping is read from that
file rather than duplicated here.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Running this file directly puts scripts/ rather than the repo root on
# sys.path, so the repo-root imports below need the root added first.
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from hub.catalogue import load_catalogue  # noqa: E402

OUT = ROOT / "tests" / "baseline_render.json"
GATE = ROOT / "tests" / "test_extraction_faithful.py"

# The element collections AppTest exposes that carry rendered content. Text is
# recorded for the ones that have a string value; the rest are counted only.
TEXT_KINDS = ("title", "header", "subheader", "markdown", "info", "warning",
              "error", "success", "caption", "code", "text")
COUNT_KINDS = TEXT_KINDS + ("dataframe", "table", "metric", "button", "checkbox",
                            "selectbox", "slider", "multiselect", "radio",
                            "number_input", "text_input", "toggle", "tabs",
                            "columns", "expander")


def baseline_keys() -> dict[str, str]:
    """current experiment id -> the baseline key it is recorded under."""
    spec = importlib.util.spec_from_file_location("_gate", GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return dict(gate.EXTRACTED)


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


def capture() -> dict:
    keys = baseline_keys()
    catalogue = load_catalogue()

    unknown = sorted(set(catalogue) - set(keys))
    if unknown:
        raise SystemExit(
            "these experiments have no baseline key, add them to EXTRACTED in "
            f"{GATE.relative_to(ROOT)} first: " + ", ".join(unknown)
        )

    captured = {}
    for exp_id in sorted(catalogue):
        app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
        if app.exception:
            raise SystemExit(
                f"{exp_id} raised while capturing: "
                + "; ".join(e.message for e in app.exception)
            )
        captured[keys[exp_id]] = observe(app)
        print(f"  captured {exp_id}")
    return captured


def main(check_only: bool) -> None:
    captured = capture()
    current = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    # Compare the FULL recorded entry (text and counts), not just text. A
    # counts-only change -- e.g. a widget disappearing without touching any
    # rendered string -- is still a change to what gets written, and must be
    # visible here or --check gives a false "nothing to see" while accept
    # bakes it in anyway.
    changed = sorted(
        key for key in captured
        if current.get(key, {}) != captured[key]
    )
    # A key present in the current baseline but not in what was just
    # captured (the experiment's catalogue key disappeared, or the
    # experiment itself did) is dropped silently by the write below unless
    # it is reported here too.
    removed = sorted(set(current) - set(captured))

    if not changed and not removed:
        print(f"no change: all {len(captured)} experiments match the baseline")
        return

    for key in changed:
        before_entry = current.get(key, {})
        after_entry = captured[key]
        before_text_list = before_entry.get("text", [])
        after_text_list = after_entry.get("text", [])
        before_text = set(before_text_list)
        after_text = set(after_text_list)
        # A pure reordering leaves these sets equal even though the entries
        # (compared as ordered lists above, in `changed`) differ -- that is
        # still a text change, not a counts-only one.
        reordered = before_text == after_text and before_text_list != after_text_list

        before_counts = before_entry.get("counts", {})
        after_counts = after_entry.get("counts", {})
        moved_counts = sorted(
            k for k in set(before_counts) | set(after_counts)
            if before_counts.get(k) != after_counts.get(k)
        )

        if before_text != after_text:
            kind = "text+counts" if moved_counts else "text"
            print(f"\n{key} [{kind}]: -{len(before_text - after_text)} +{len(after_text - before_text)}")
            for text in sorted(before_text - after_text)[:3]:
                print(f"  - {text[:90]}")
            for text in sorted(after_text - before_text)[:3]:
                print(f"  + {text[:90]}")
            for count_key in moved_counts:
                print(f"  counts.{count_key}: {before_counts.get(count_key)} -> {after_counts.get(count_key)}")
        elif reordered:
            kind = "text-reorder+counts" if moved_counts else "text-reorder"
            print(f"\n{key} [{kind}]: same strings, different order")
            for count_key in moved_counts:
                print(f"  counts.{count_key}: {before_counts.get(count_key)} -> {after_counts.get(count_key)}")
        else:
            # Text is byte-identical and in the same order; only element
            # counts moved. Report what moved and between what values so
            # this is distinguishable at a glance from a real content change.
            print(f"\n{key} [counts-only]:")
            for count_key in moved_counts:
                print(f"  counts.{count_key}: {before_counts.get(count_key)} -> {after_counts.get(count_key)}")

    for key in removed:
        print(f"\n{key} [removed]: no longer produced by the catalogue")

    if check_only:
        total = len(changed) + len(removed)
        print(f"\n--check: {total} experiment(s) would be rewritten "
              f"({len(changed)} changed, {len(removed)} removed)")
        return

    OUT.write_text(json.dumps(captured, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nrewrote {OUT.relative_to(ROOT)} for {len(changed)} experiment(s), "
          f"dropped {len(removed)} removed key(s)")


if __name__ == "__main__":
    main("--check" in sys.argv)
