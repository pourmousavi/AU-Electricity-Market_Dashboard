# Standalone Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six vendored dashboards with 25 standalone, content-named experiment modules that the hub owns and edits directly.

**Architecture:** Each experiment becomes `experiments/<id>.py` exposing `render()`. Code used by exactly one experiment lives in that experiment's file; the three genuinely shared page bodies become `experiments/_kit/{dispatch,dc_network,duality}.py`. `hub/runner.py` reduces to import-and-call, which deletes the selectbox/tab monkeypatching, the AST tab surgery and the global render lock. `catalogue.yaml` is replaced by a glob over `experiments/`.

**Tech Stack:** Python 3.12, Streamlit (>=1.50,<1.62), SQLAlchemy Core + Neon Postgres, pytest, `streamlit.testing.v1.AppTest`, `ast` for the one-off extraction.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-12-standalone-experiments-design.md`. Read it before Task 1.
- No behaviour or visual changes. The extraction is faithful; the only intended difference from today is the dropped sidebar branding (weeks 2, 3, 4).
- Extracted code is moved **verbatim**. Do not reformat, rename, fix lint, modernise Streamlit calls, or "improve" anything while extracting. Cleanups happen later, on their own, against a green baseline.
- Every experiment module exposes `def render() -> None:` and must never call `st.set_page_config`.
- Experiment ids and filenames come from the rename table in Task 10. They are the DB primary key — do not invent new ones.
- Run tests with `.venv/bin/python -m pytest`. The full suite currently passes at 196 tests.
- The venv already has every dependency the dashboards need (cvxpy, networkx, sympy, scipy, plotly, matplotlib). Do not add or upgrade packages.
- `git mv`/`git rm` the old files rather than deleting and re-adding, so history follows.

---

### Task 1: Capture the rendering baseline

Nothing can be verified as "faithful" without a record of what each experiment renders today. This task produces that record while the old code still works.

**Files:**
- Create: `scripts/capture_baseline.py`
- Create: `tests/baseline_render.json` (generated, committed)

**Interfaces:**
- Produces: `tests/baseline_render.json`, a dict keyed by **old** experiment id, each value `{"counts": {<element type>: int}, "text": [str, ...]}`. Tasks 3–8 read it.

- [ ] **Step 1: Write the capture script**

```python
"""Record what every experiment renders TODAY, before the split.

Run once, from the repo root, while the old runner/catalogue still exist:

    .venv/bin/python scripts/capture_baseline.py

The output is committed and used by tests/test_extraction_faithful.py to prove
each extracted module renders the same thing as the bundle it came from.
"""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from hub.catalogue import load_catalogue

ROOT = Path(__file__).resolve().parent.parent
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
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/capture_baseline.py`
Expected: 25 "captured ..." lines, then "wrote .../baseline_render.json for 25 experiments". Takes several minutes — weeks 7 and 8 run real solvers.

- [ ] **Step 3: Sanity-check the baseline is not empty**

Run: `.venv/bin/python -c "import json;d=json.load(open('tests/baseline_render.json'));print(len(d), min(len(v['text']) for v in d.values()))"`
Expected: `25` and a second number greater than `0` — if any experiment recorded zero text, stop and investigate before extracting anything.

- [ ] **Step 4: Commit**

```bash
git add scripts/capture_baseline.py tests/baseline_render.json
git commit -m "test: record pre-split rendering baseline for all 25 experiments"
```

---

### Task 2: The extraction tool

25 hand-extractions would introduce hand-extraction mistakes. This tool computes the dependency closure — which top-level helpers, constants and imports a given block of code actually needs — so the extraction is mechanical.

**Files:**
- Create: `scripts/extract_experiment.py`
- Test: `tests/test_extract_experiment.py`

**Interfaces:**
- Produces:
  - `closure(tree: ast.Module, roots: list[ast.stmt]) -> list[ast.stmt]` — the top-level `FunctionDef`/`ClassDef`/`Assign` statements reachable from `roots`, in source order.
  - `build_module(source: str, body: list[ast.stmt], roots: list[ast.stmt], docstring: str) -> str` — the text of a new module: docstring, all imports from the source, the closure, then `def render() -> None:` wrapping `body`.
- Tasks 3–8 call these.

- [ ] **Step 1: Write the failing test**

```python
"""The extractor must pull in what a block needs, and nothing it doesn't."""
import ast

from scripts.extract_experiment import build_module, closure

SOURCE = '''\
import streamlit as st
import numpy as np

CONSTANT = {"a": 1}
OTHER = 42


def helper(x):
    return x * CONSTANT["a"]


def unrelated(x):
    return x + OTHER


def section():
    st.write(helper(2))
'''


def test_closure_pulls_transitive_dependencies() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    names = {getattr(n, "name", None) or n.targets[0].id
             for n in closure(tree, [section])}
    assert names == {"helper", "CONSTANT"}


def test_closure_excludes_unreachable_helpers() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    names = {getattr(n, "name", None) or n.targets[0].id
             for n in closure(tree, [section])}
    assert "unrelated" not in names and "OTHER" not in names


def test_build_module_emits_render_with_the_body() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    out = build_module(SOURCE, section.body, [section], "Extracted test.")
    assert out.startswith('"""Extracted test.')
    assert "import streamlit as st" in out
    assert "def helper(x):" in out
    assert "def unrelated" not in out
    assert "def render() -> None:" in out
    assert "    st.write(helper(2))" in out
    compile(out, "<extracted>", "exec")  # must be valid Python
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_experiment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract_experiment'`

- [ ] **Step 3: Write the extractor**

```python
"""AST helpers for the one-off split of the bundled dashboards.

Given a block of statements to become an experiment's render() body, work out
which top-level functions, classes and constants it transitively needs, and
emit a standalone module. Code is copied verbatim via ast.unparse of the
original nodes -- no reformatting, no rewriting.
"""
from __future__ import annotations

import ast
import textwrap


def _names_used(nodes: list[ast.stmt]) -> set[str]:
    used = set()
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                used.add(sub.id)
            elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                used.add(sub.value.id)
    return used


def _definitions(tree: ast.Module) -> dict[str, ast.stmt]:
    """Top-level defs, classes and simple constant assignments, by name."""
    out: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node
    return out


def closure(tree: ast.Module, roots: list[ast.stmt]) -> list[ast.stmt]:
    """Every top-level definition reachable from `roots`, in source order."""
    defined = _definitions(tree)
    needed: set[str] = set()
    frontier = _names_used(roots)

    while frontier:
        name = frontier.pop()
        if name in needed or name not in defined:
            continue
        needed.add(name)
        frontier |= _names_used([defined[name]])

    root_ids = {id(node) for node in roots}
    picked, seen = [], set()
    for node in tree.body:
        if id(node) in root_ids or id(node) in seen:
            continue
        for name in needed:
            if defined.get(name) is node:
                picked.append(node)
                seen.add(id(node))
                break
    return picked


def imports(tree: ast.Module) -> list[ast.stmt]:
    """All module-level imports, kept wholesale.

    Deliberately not pruned to what is used: a missing import is a crash, an
    extra one is a lint note. Prune by hand later if it matters.
    """
    return [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]


def session_state_guards(tree: ast.Module) -> list[ast.stmt]:
    """Module-level `if 'key' not in st.session_state:` initialisation blocks.

    These run before anything else in the original module, so they go at the
    top of render(). They are idempotent, so all of them are carried.
    """
    out = []
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.ops[0], ast.NotIn)
                and "session_state" in ast.unparse(test.comparators[0])):
            out.append(node)
    return out


def build_module(source: str, body: list[ast.stmt], roots: list[ast.stmt],
                 docstring: str, extra_head: str = "") -> str:
    """Render the text of a standalone experiment module."""
    tree = ast.parse(source)
    parts = [f'"""{docstring}"""', ""]
    parts += [ast.unparse(node) for node in imports(tree)]
    if extra_head:
        parts += ["", extra_head]
    parts.append("")
    for node in closure(tree, roots):
        parts += [ast.unparse(node), ""]

    guards = session_state_guards(tree)
    lines = [ast.unparse(node) for node in guards + body] or ["pass"]
    parts += ["def render() -> None:",
              textwrap.indent("\n".join(lines), "    "), ""]
    return "\n".join(parts)
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest tests/test_extract_experiment.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_experiment.py tests/test_extract_experiment.py
git commit -m "feat: add AST extractor for splitting bundled dashboards"
```

---

### Task 3: The faithfulness check

The check that every later task runs. Written once, here, so extraction tasks have something to fail against.

**Files:**
- Create: `tests/test_extraction_faithful.py`

**Interfaces:**
- Consumes: `tests/baseline_render.json` (Task 1), `EXTRACTED` map below.
- Produces: `EXTRACTED: dict[str, str]` mapping **new** id → **old** id. Tasks 4–9 add one line per experiment they extract.

- [ ] **Step 1: Write the check**

```python
"""Each extracted module must render what its bundled original rendered.

Tasks add a line to EXTRACTED as they extract. An experiment that is not in
this map yet is simply not checked -- the map grows to 25 by the end of the
split, and test_every_experiment_is_checked then locks it.
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
BASELINE = json.loads((ROOT / "tests" / "baseline_render.json").read_text())

# new id -> old id. One line added per extracted experiment.
EXTRACTED: dict[str, str] = {}

# Text the extraction deliberately drops: the vendored sidebar branding of
# weeks 2, 3 and 4. Any other missing text is a defect.
ALLOWED_REMOVALS = {
    "⚡ Electricity Market Dashboard",
    "📈 3D Optimization Dashboard",
    "---",
    "### Course Information",
    "**Electricity Market and Power Systems Operation**",
    "**ELEC ENG 4087/7087**",
    "**Course Coordinator & Creator:**",
    "Ali Pourmousavi Kani",
    "**Version:** 2.0",
    "**Version:** 1.0 - Market Power & Economics",
    "**Version:** 2.0 - 3D Nonlinear Optimization",
}


def _harness(new_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import importlib\n"
        f"module = importlib.import_module('experiments.{new_id}')\n"
        "module.render()\n"
    )


def _render(new_id: str):
    app = AppTest.from_string(_harness(new_id), default_timeout=180).run()
    assert not app.exception, (
        f"{new_id} raised: " + "; ".join(e.message for e in app.exception)
    )
    return app


@pytest.mark.parametrize("new_id", sorted(EXTRACTED))
def test_extracted_module_renders_its_baseline_text(new_id: str) -> None:
    app = _render(new_id)
    rendered = set()
    for kind in ("title", "header", "subheader", "markdown", "info", "warning",
                 "error", "success", "caption", "code", "text"):
        for element in getattr(app, kind, []):
            value = getattr(element, "value", None)
            if isinstance(value, str):
                rendered.add(value)

    expected = set(BASELINE[EXTRACTED[new_id]]["text"])
    missing = {t for t in expected - rendered if t.strip() not in ALLOWED_REMOVALS}
    assert not missing, (
        f"{new_id} no longer renders {len(missing)} baseline strings, e.g. "
        + repr(sorted(missing)[:3])
    )


def test_every_experiment_is_checked() -> None:
    """Once the split is done, all 25 must be covered. Fails until then."""
    assert len(EXTRACTED) == 25, f"only {len(EXTRACTED)}/25 extracted so far"
```

- [ ] **Step 2: Run it — it must fail on the last test only**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v`
Expected: `test_every_experiment_is_checked` FAILS with "only 0/25 extracted so far". No other failures. That failure is the progress meter for Tasks 4–9.

- [ ] **Step 3: Commit**

```bash
git add tests/test_extraction_faithful.py
git commit -m "test: add baseline faithfulness check for extracted experiments"
```

---

### Task 4: Extract week 2 — five experiments

**Files:**
- Create: `experiments/__init__.py` (empty), `experiments/_kit/__init__.py` (empty)
- Create: `experiments/consumer_model.py`, `experiments/consumer_elasticity.py`, `experiments/supplier_model.py`, `experiments/supplier_elasticity.py`, `experiments/market_equilibrium.py`
- Modify: `tests/test_extraction_faithful.py` (add 5 lines to `EXTRACTED`)
- Read: `sources/week2_consumer_supplier.py`

**Interfaces:**
- Consumes: `scripts.extract_experiment.build_module`, `closure` (Task 2).
- Produces: five modules each exposing `render() -> None`.

Source map — entry function per experiment (all are top-level `*_section()` functions whose body becomes `render()`):

| New file | Entry function | Lines |
|---|---|---|
| consumer_model.py | `consumer_model_section` | 786–995 |
| supplier_model.py | `supplier_model_section` | 996–1195 |
| consumer_elasticity.py | `consumer_elasticity_section` | 1196–1370 |
| market_equilibrium.py | `market_equilibrium_section` | 1371–1669 |
| supplier_elasticity.py | `supplier_elasticity_section` | 1670–1839 |

`calculate_elasticity` is reached by two of these; per the spec it is copied into both rather than promoted to `_kit`.

- [ ] **Step 1: Create the packages**

```bash
mkdir -p experiments/_kit
touch experiments/__init__.py experiments/_kit/__init__.py
```

- [ ] **Step 2: Write and run the extraction driver**

Create `scripts/_split_week2.py` (a scratch driver, deleted in Step 6):

```python
import ast
from pathlib import Path

from scripts.extract_experiment import build_module

SOURCE = Path("sources/week2_consumer_supplier.py")
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)

TARGETS = {
    "consumer_model": "consumer_model_section",
    "supplier_model": "supplier_model_section",
    "consumer_elasticity": "consumer_elasticity_section",
    "market_equilibrium": "market_equilibrium_section",
    "supplier_elasticity": "supplier_elasticity_section",
}

for new_id, entry in TARGETS.items():
    node = next(n for n in TREE.body
                if isinstance(n, ast.FunctionDef) and n.name == entry)
    text = build_module(
        TEXT, node.body, [node],
        f"{new_id.replace('_', ' ').title()}.\n\n"
        f"Extracted from {SOURCE.name} ({entry}) on 2026-08-12.",
    )
    out = Path("experiments") / f"{new_id}.py"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text.splitlines())} lines)")
```

Run: `.venv/bin/python -m scripts._split_week2`
Expected: five "wrote experiments/..." lines.

- [ ] **Step 3: Register the five in the faithfulness check**

In `tests/test_extraction_faithful.py`, set:

```python
EXTRACTED: dict[str, str] = {
    "consumer_model": "w2.consumer_model",
    "consumer_elasticity": "w2.consumer_elasticity",
    "supplier_model": "w2.supplier_model",
    "supplier_elasticity": "w2.supplier_elasticity",
    "market_equilibrium": "w2.market_equilibrium",
}
```

- [ ] **Step 4: Run the check**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v -k "not every_experiment"`
Expected: 5 passed.

If one fails on missing text, the cause is almost always a name the closure missed because it is reached dynamically (a string key, a `globals()` lookup). Read the reported missing strings, find the helper that produces them in the source, and append that function's `ast.unparse` output to the generated file by hand. Do not edit the copied code itself.

- [ ] **Step 5: Confirm no `set_page_config` leaked in**

Run: `grep -n "set_page_config" experiments/*.py`
Expected: no output.

- [ ] **Step 6: Delete the scratch driver and commit**

```bash
rm scripts/_split_week2.py
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 2's five experiments into standalone modules"
```

---

### Task 5: Extract week 3 — four experiments

**Files:**
- Create: `experiments/pool_pricing.py`, `experiments/market_power.py`, `experiments/profit_cost_recovery.py`, `experiments/interactive_clearing.py`
- Modify: `tests/test_extraction_faithful.py`
- Read: `sources/week3_pricing_market_power.py`

**Interfaces:**
- Consumes: `scripts.extract_experiment.build_module` (Task 2).
- Produces: four modules each exposing `render() -> None`.

| New file | Entry function | Lines |
|---|---|---|
| pool_pricing.py | `pool_market_pricing_section` | 715–923 |
| market_power.py | `market_power_analysis_section` | 924–1007 |
| profit_cost_recovery.py | `profit_cost_recovery_section` | 1008–1134 |
| interactive_clearing.py | `interactive_market_clearing_section` | 1135–1338 |

Note: this file has a module-level constant `COURSE_GENERATORS` (line 149) — `closure()` picks it up automatically for the experiments that reference it. It also has trailing module-level markdown after `main()` (lines 2049–2050) which is footer chrome; it is **not** carried into any experiment.

- [ ] **Step 1: Write and run the driver**

Create `scripts/_split_week3.py`:

```python
import ast
from pathlib import Path

from scripts.extract_experiment import build_module

SOURCE = Path("sources/week3_pricing_market_power.py")
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)

TARGETS = {
    "pool_pricing": "pool_market_pricing_section",
    "market_power": "market_power_analysis_section",
    "profit_cost_recovery": "profit_cost_recovery_section",
    "interactive_clearing": "interactive_market_clearing_section",
}

for new_id, entry in TARGETS.items():
    node = next(n for n in TREE.body
                if isinstance(n, ast.FunctionDef) and n.name == entry)
    text = build_module(
        TEXT, node.body, [node],
        f"{new_id.replace('_', ' ').title()}.\n\n"
        f"Extracted from {SOURCE.name} ({entry}) on 2026-08-12.",
    )
    out = Path("experiments") / f"{new_id}.py"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text.splitlines())} lines)")
```

Run: `.venv/bin/python -m scripts._split_week3`
Expected: four "wrote experiments/..." lines.

- [ ] **Step 2: Register them**

Add to `EXTRACTED` in `tests/test_extraction_faithful.py`:

```python
    "pool_pricing": "w3.pool_pricing",
    "market_power": "w3.market_power",
    "profit_cost_recovery": "w3.profit_cost_recovery",
    "interactive_clearing": "w3.interactive_clearing",
```

- [ ] **Step 3: Run the check**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v -k "not every_experiment"`
Expected: 9 passed.

- [ ] **Step 4: Delete the driver and commit**

```bash
rm scripts/_split_week3.py
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 3's four experiments into standalone modules"
```

---

### Task 6: Extract week 4 — two experiments

Week 4 has no section functions: both experiments are inline blocks under `if page_option == ...` at module level, and the "Modelling Tools Comparison" one builds its own internal `st.tabs` (which stays — nothing patches `st.tabs` any more).

**Files:**
- Create: `experiments/modelling_tools_comparison.py`, `experiments/nonlinear_optimisation_3d.py`
- Modify: `tests/test_extraction_faithful.py`
- Read: `sources/week4_optimisation_tools.py`

**Interfaces:**
- Consumes: `scripts.extract_experiment.build_module` (Task 2).
- Produces: two modules each exposing `render() -> None`.

| New file | Inline block | Lines |
|---|---|---|
| modelling_tools_comparison.py | `if page_option == "Modelling Tools Comparison":` body | 576–990 |
| nonlinear_optimisation_3d.py | its `elif page_option == "3D Nonlinear Optimization":` body | 991–1221 |

- [ ] **Step 1: Write and run the driver**

Create `scripts/_split_week4.py`:

```python
import ast
from pathlib import Path

from scripts.extract_experiment import build_module

SOURCE = Path("sources/week4_optimisation_tools.py")
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)

dispatch = next(n for n in TREE.body
                if isinstance(n, ast.If) and "page_option" in ast.unparse(n.test))

BLOCKS = {
    "modelling_tools_comparison": dispatch.body,
    "nonlinear_optimisation_3d": dispatch.orelse[0].body,
}

for new_id, body in BLOCKS.items():
    text = build_module(
        TEXT, body, body,
        f"{new_id.replace('_', ' ').title()}.\n\n"
        f"Extracted from {SOURCE.name} on 2026-08-12.",
    )
    out = Path("experiments") / f"{new_id}.py"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text.splitlines())} lines)")
```

Run: `.venv/bin/python -m scripts._split_week4`
Expected: two "wrote experiments/..." lines.

If `dispatch.orelse[0]` is not the `elif` (i.e. the file's structure differs from the line numbers above), print `ast.dump` of the dispatch node and pick the right branch rather than guessing.

- [ ] **Step 2: Register them**

```python
    "modelling_tools_comparison": "w4.tools_comparison",
    "nonlinear_optimisation_3d": "w4.nonlinear_3d",
```

- [ ] **Step 3: Run the check**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v -k "not every_experiment"`
Expected: 11 passed.

- [ ] **Step 4: Delete the driver and commit**

```bash
rm scripts/_split_week4.py
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 4's two experiments into standalone modules"
```

---

### Task 7: Extract week 6 — shared duality page plus three experiments

The hardest shape. The whole 544-line module is one page; the three experiments are tab bodies at lines 394–411, 412–436 and 437–464. Everything else is common and becomes `_kit/duality.py`.

**Files:**
- Create: `experiments/_kit/duality.py`
- Create: `experiments/strong_duality.py`, `experiments/weak_duality.py`, `experiments/duality_theorems.py`
- Modify: `tests/test_extraction_faithful.py`
- Read: `sources/week6_duality.py`

**Interfaces:**
- Produces: `experiments._kit.duality.page() -> tuple`, returning `(primal_x, primal_obj, dual_lambda, dual_obj)` — the values the post-tab sections use.
- Produces: three modules each exposing `render() -> None` and `STATE_GROUP = "duality"`.

This one is done by hand, not by driver script, because the split point is inside module-level flow rather than at a definition boundary.

- [ ] **Step 1: Build `_kit/duality.py`**

Copy `sources/week6_duality.py` to `experiments/_kit/duality.py`, then:

1. Delete the `st.set_page_config(...)` call (line 11).
2. Delete the `st.tabs([...])` call and the three `with tab1/tab2/tab3:` blocks (lines 389–464), leaving a marker comment `# tab bodies now live in the three duality experiment modules`.
3. Wrap everything that remains below the imports and the top-level `def`s in:

```python
def page() -> tuple:
    """Render the shared duality page and return what the tab sections need."""
```

with the original module-level statements indented one level as its body, ending with:

```python
    return primal_x, primal_obj, dual_lambda, dual_obj
```

4. Leave `solve_primal`, `solve_dual` and `create_3d_plot` as top-level functions.

- [ ] **Step 2: Build the three experiment modules**

`experiments/strong_duality.py`:

```python
"""Strong Duality.

Extracted from week6_duality.py (tab 1) on 2026-08-12. The page body it shares
with the other two duality experiments lives in experiments/_kit/duality.py.
"""
import streamlit as st

from experiments._kit import duality

STATE_GROUP = "duality"


def render() -> None:
    primal_x, primal_obj, dual_lambda, dual_obj = duality.page()
    # <lines 394-411 of sources/week6_duality.py, dedented one level, verbatim>
```

Repeat for `weak_duality.py` (lines 412–436) and `duality_theorems.py` (lines 437–464), each with the same header shape and `STATE_GROUP = "duality"`.

If a pasted tab body does not reference `primal_x` / `dual_lambda`, drop the unused names from the unpacking rather than leaving unused locals.

- [ ] **Step 3: Register them**

```python
    "strong_duality": "w6.strong_duality",
    "weak_duality": "w6.weak_duality",
    "duality_theorems": "w6.duality_theorems",
```

- [ ] **Step 4: Run the check**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v -k "not every_experiment"`
Expected: 14 passed.

- [ ] **Step 5: Verify the tab bodies did not cross-contaminate**

Run: `.venv/bin/python -m pytest tests/test_experiments_render.py -k "w6" -v`
Expected: still passes against the old runner (untouched until Task 10). Then check by hand:

Run: `grep -c "When does strong duality hold?" experiments/strong_duality.py experiments/weak_duality.py experiments/duality_theorems.py`
Expected: `1`, `0`, `0` — that marker belongs to tab 1 only.

- [ ] **Step 6: Commit**

```bash
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 6 into a shared duality page and three experiments"
```

---

### Task 8: Extract week 7 — dispatch kit plus five experiments

**Files:**
- Create: `experiments/_kit/dispatch.py`
- Create: `experiments/dispatch_generator_setup.py`, `experiments/dispatch_comparison.py`, `experiments/dispatch_detailed_analysis.py`, `experiments/dispatch_individual_generators.py`, `experiments/dispatch_pareto_frontier.py`
- Modify: `tests/test_extraction_faithful.py`
- Read: `sources/week7_ed_viu.py`

**Interfaces:**
- Produces: `experiments._kit.dispatch.preamble() -> None` — runs `initialize_session_state()`, the module's CSS markdown block (lines 21+), and `render_sidebar()`, exactly as `main()` does today.
- Produces: five modules each exposing `render() -> None` and `STATE_GROUP = "dispatch"`.

| New file | Tab function | Old id |
|---|---|---|
| dispatch_generator_setup.py | `render_generator_table` | w7.generator_setup |
| dispatch_comparison.py | `render_comparison_results` | w7.comparison_results |
| dispatch_detailed_analysis.py | `render_detailed_analysis` | w7.detailed_analysis |
| dispatch_individual_generators.py | `render_individual_generator_analysis` | w7.individual_generators |
| dispatch_pareto_frontier.py | `render_pareto_frontier` | w7.pareto |

- [ ] **Step 1: Build `_kit/dispatch.py`**

Copy into it, verbatim from the source: `initialize_session_state` (648–668), `create_demand_profile` (669–688), `render_sidebar` (689–757), `solve_all_problems` (758–780), `get_problem_name` (1062–1072), `get_problem_description` (1073–1084), plus the module's imports and its module-level `st.markdown` CSS block (line 21) assigned to a module constant `PAGE_CSS`. Then add:

```python
def preamble() -> None:
    """Everything week 7's main() did before drawing its tabs."""
    initialize_session_state()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    render_sidebar()
```

Read `main()` (1614–1696) and reproduce its pre-tab statements in `preamble()` in the same order. If `main()` calls `solve_all_problems()` before the tabs, call it here too.

- [ ] **Step 2: Build the five experiment modules**

Each has this shape — for `dispatch_comparison.py`:

```python
"""Dispatch comparison results.

Extracted from week7_ed_viu.py (render_comparison_results) on 2026-08-12.
The sidebar, session state and solve step shared with the other dispatch
experiments live in experiments/_kit/dispatch.py.
"""
import streamlit as st

from experiments._kit import dispatch

STATE_GROUP = "dispatch"


def render() -> None:
    dispatch.preamble()
    # <body of render_comparison_results, dedented one level, verbatim>
```

Any helper the body calls that is *not* in `_kit/dispatch.py` (e.g. `count_ramping_violations` for the detailed-analysis experiment) is copied into that experiment's own file, since it has exactly one consumer. Use the extractor's `closure()` to find them rather than reading by eye.

- [ ] **Step 3: Register the five**

```python
    "dispatch_generator_setup": "w7.generator_setup",
    "dispatch_comparison": "w7.comparison_results",
    "dispatch_detailed_analysis": "w7.detailed_analysis",
    "dispatch_individual_generators": "w7.individual_generators",
    "dispatch_pareto_frontier": "w7.pareto",
```

- [ ] **Step 4: Run the check**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v -k "not every_experiment"`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 7 into a dispatch kit and five experiments"
```

---

### Task 9: Extract week 8 — DC network kit plus six experiments

**Files:**
- Create: `experiments/_kit/dc_network.py`
- Create: `experiments/auction_market_setup.py`, `experiments/auction_network_topology.py`, `experiments/auction_market_results.py`, `experiments/dc_opf_results.py`, `experiments/auction_vs_dc_opf.py`, `experiments/power_flow_theory.py`
- Modify: `tests/test_extraction_faithful.py`
- Read: `sources/week8_pf_auction.py`

**Interfaces:**
- Produces: `experiments._kit.dc_network.preamble() -> None`, mirroring week 8's `main()` before its tabs.
- Produces: six modules each exposing `render() -> None` and `STATE_GROUP = "dc_network"`.

| New file | Tab function | Old id |
|---|---|---|
| auction_market_setup.py | `render_market_setup` | w8.market_setup |
| auction_network_topology.py | `render_network_topology` | w8.network_topology |
| auction_market_results.py | `render_market_results` | w8.market_results |
| dc_opf_results.py | `render_dc_opf_results` | w8.dc_opf_results |
| auction_vs_dc_opf.py | `render_market_vs_optimal_comparison` | w8.market_vs_opf |
| power_flow_theory.py | the sixth tab's inline body | w8.theory |

Into `_kit/dc_network.py`, verbatim: `initialize_session_state` (1078–1160), `render_sidebar` (1162–1187), `solve_market` (1188–1213), `solve_optimal_dc_power_flow` (957–1001), `calculate_market_dc_power_flow` (1002–1077), `render_power_flow_results` (1891–1953), the imports, and the module-level CSS block as `PAGE_CSS`. `_update_bus_configuration`, `_regenerate_generators_list` and `_regenerate_retailers_list` belong to the network-topology experiment alone — copy them into that file.

The sixth tab ("📚 Theory & Concepts") has no function of its own; its body is inline in `main()` around line 2571. Lift that block into `power_flow_theory.py`'s `render()`.

- [ ] **Step 1: Build `_kit/dc_network.py`** as described, with `preamble()` reproducing `main()`'s pre-tab statements in order.

- [ ] **Step 2: Build the six experiment modules**, each following the Task 8 Step 2 shape with `STATE_GROUP = "dc_network"`.

- [ ] **Step 3: Register the six**

```python
    "auction_market_setup": "w8.market_setup",
    "auction_network_topology": "w8.network_topology",
    "auction_market_results": "w8.market_results",
    "dc_opf_results": "w8.dc_opf_results",
    "auction_vs_dc_opf": "w8.market_vs_opf",
    "power_flow_theory": "w8.theory",
```

- [ ] **Step 4: Run the full faithfulness check, including the gate**

Run: `.venv/bin/python -m pytest tests/test_extraction_faithful.py -v`
Expected: 26 passed — 25 per-experiment checks plus `test_every_experiment_is_checked`, which now passes because `EXTRACTED` has 25 entries.

- [ ] **Step 5: Commit**

```bash
git add experiments tests/test_extraction_faithful.py
git commit -m "feat: extract week 8 into a DC network kit and six experiments"
```

---

### Task 10: Switch the hub over — catalogue, runner, state groups, ids

All 25 modules now exist and are verified. This task points the hub at them and migrates the database in the same change.

**Files:**
- Rewrite: `hub/catalogue.py`, `hub/runner.py`
- Modify: `hub/db.py:84-130` (`_default_title`, `seed_initial`)
- Create: `scripts/migrate_experiment_ids.py`
- Modify: `tests/test_catalogue.py`, `tests/test_runner_units.py`, `tests/test_experiments_render.py`
- Delete: `catalogue.yaml`

**Interfaces:**
- Produces: `hub.catalogue.Experiment(id: str, path: Path)` — `source_key`, `source_path`, `mode`, `selector` and `entry` are gone.
- Produces: `hub.runner.render_experiment(exp: Experiment) -> None`, unchanged signature so `hub/pages_experiment.py` needs no edit.

Rename table (old id → new id / filename):

| Old | New | | Old | New |
|---|---|---|---|---|
| w2.consumer_model | consumer_model | | w7.generator_setup | dispatch_generator_setup |
| w2.consumer_elasticity | consumer_elasticity | | w7.comparison_results | dispatch_comparison |
| w2.supplier_model | supplier_model | | w7.detailed_analysis | dispatch_detailed_analysis |
| w2.supplier_elasticity | supplier_elasticity | | w7.individual_generators | dispatch_individual_generators |
| w2.market_equilibrium | market_equilibrium | | w7.pareto | dispatch_pareto_frontier |
| w3.pool_pricing | pool_pricing | | w8.market_setup | auction_market_setup |
| w3.market_power | market_power | | w8.network_topology | auction_network_topology |
| w3.profit_cost_recovery | profit_cost_recovery | | w8.market_results | auction_market_results |
| w3.interactive_clearing | interactive_clearing | | w8.dc_opf_results | dc_opf_results |
| w4.nonlinear_3d | nonlinear_optimisation_3d | | w8.market_vs_opf | auction_vs_dc_opf |
| w4.tools_comparison | modelling_tools_comparison | | w8.theory | power_flow_theory |
| w6.strong_duality | strong_duality | | | |
| w6.weak_duality | weak_duality | | | |
| w6.duality_theorems | duality_theorems | | | |

- [ ] **Step 1: Write the failing catalogue test**

Replace the body of `tests/test_catalogue.py` with:

```python
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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_catalogue.py -v`
Expected: FAIL — the old `Experiment` has no `path` attribute.

- [ ] **Step 3: Rewrite `hub/catalogue.py`**

```python
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
```

- [ ] **Step 4: Run the catalogue test**

Run: `.venv/bin/python -m pytest tests/test_catalogue.py -v`
Expected: 2 passed.

- [ ] **Step 5: Rewrite `hub/runner.py`**

```python
"""Renders one experiment module.

Each experiment is its own module in experiments/ exposing render(), so there
is nothing to isolate at runtime: no monkeypatching of the shared streamlit
module, and therefore no global lock serialising concurrent students.

Session state is still namespaced, because separate modules can pick the same
key -- `supply_bids` means different things in different experiments. Modules
that deliberately share state (the ones backed by a common experiments/_kit
page) declare the same STATE_GROUP.
"""
from __future__ import annotations

import importlib

import streamlit as st

from hub.catalogue import Experiment
from hub.state import isolate


class ExperimentRenderError(Exception):
    """An experiment could not be rendered."""


def render_experiment(exp: Experiment) -> None:
    """Render one experiment into the current Streamlit context."""
    try:
        module = importlib.import_module(f"experiments.{exp.id}")
    except Exception as exc:  # noqa: BLE001 - surfaced as a hub-level error
        raise ExperimentRenderError(f"{exp.id}: import failed: {exc}") from exc

    isolate(st.session_state, getattr(module, "STATE_GROUP", exp.id))

    render = getattr(module, "render", None)
    if not callable(render):
        raise ExperimentRenderError(f"{exp.id}: module has no callable render()")
    render()
```

- [ ] **Step 6: Rewrite `tests/test_runner_units.py`**

Delete every test covering `_pinned_selectbox`, `_pinned_tabs`, `_no_page_config`, `prepare` and `_RENDER_LOCK` — that machinery no longer exists. Keep and adapt the state-isolation coverage, and add:

```python
import pytest

from hub.catalogue import Experiment
from hub.runner import ExperimentRenderError, render_experiment


def test_missing_module_raises_render_error(tmp_path) -> None:
    exp = Experiment(id="does_not_exist", path=tmp_path / "does_not_exist.py")
    with pytest.raises(ExperimentRenderError, match="import failed"):
        render_experiment(exp)


def test_module_without_render_raises(monkeypatch) -> None:
    import sys
    import types

    module = types.ModuleType("experiments.no_render")
    sys.modules["experiments.no_render"] = module
    try:
        exp = Experiment(id="no_render", path=__file__)
        with pytest.raises(ExperimentRenderError, match="no callable render"):
            render_experiment(exp)
    finally:
        del sys.modules["experiments.no_render"]


def test_state_group_defaults_to_the_experiment_id() -> None:
    import sys
    import types

    import streamlit as st

    module = types.ModuleType("experiments.grouped")
    module.STATE_GROUP = "dispatch"
    module.render = lambda: None
    sys.modules["experiments.grouped"] = module
    try:
        render_experiment(Experiment(id="grouped", path=__file__))
        assert st.session_state["_hub.active_source"] == "dispatch"
    finally:
        del sys.modules["experiments.grouped"]
```

- [ ] **Step 7: Update `tests/test_experiments_render.py`**

Change `_harness` to import the module and call `render()` (same body as `tests/test_extraction_faithful.py::_harness`), and rewrite `PIN_TAB_MARKERS` keys to the new ids — the marker strings themselves are unchanged and still valuable: they assert each experiment renders its own content and none of its former siblings'. Replace the `mode == "pin_tab"` filter with an explicit list of the 14 ids that were tab-based, and replace `_SIBLINGS_BY_SOURCE` with grouping by `STATE_GROUP`.

- [ ] **Step 8: Fix `hub/db.py`**

`_default_title` currently splits on `.` to drop the `w2.` prefix. New ids have no prefix:

```python
def _default_title(experiment_id: str) -> str:
    return experiment_id.replace("_", " ").title()
```

`seed_initial` groups by `exp.source_key`, which no longer exists. It only runs on a genuinely empty database, so put every experiment in one topic and let the admin panel sort it:

```python
        result = conn.execute(insert(topic).values(
            name="Unsorted", subtitle="Assign these to topics in the admin panel.",
            unlock_message="Not available yet.", sort_order=0, enabled=False,
        ))
        unsorted_id = int(result.inserted_primary_key[0])

        for order, exp in enumerate(catalogue.values()):
            conn.execute(insert(experiment).values(
                experiment_id=exp.id, topic_id=unsorted_id,
                title=_default_title(exp.id), blurb="",
                sort_order=order, enabled=False, orphaned=False,
            ))
```

Delete `_SEED_TOPICS` and `_TOPIC_NAMES` if nothing else uses them, and update `tests/test_db.py` where it asserts six seeded topics.

- [ ] **Step 9: Write the id migration script**

```python
"""One-time rename of experiment ids after the standalone-experiments split.

Run ONCE against the live database, immediately before deploying the new code:

    .venv/bin/python scripts/migrate_experiment_ids.py --dry-run
    .venv/bin/python scripts/migrate_experiment_ids.py

Idempotent: ids already migrated are skipped. Ids not in the map are left
alone and reported. Aborts if a new id already exists while its old id also
does -- that means the new code booted before the migration and inserted blank
rows, which must be resolved by hand.
"""
from __future__ import annotations

import sys

from sqlalchemy import select, update

from hub import db

RENAMES = {
    "w2.consumer_model": "consumer_model",
    "w2.consumer_elasticity": "consumer_elasticity",
    "w2.supplier_model": "supplier_model",
    "w2.supplier_elasticity": "supplier_elasticity",
    "w2.market_equilibrium": "market_equilibrium",
    "w3.pool_pricing": "pool_pricing",
    "w3.market_power": "market_power",
    "w3.profit_cost_recovery": "profit_cost_recovery",
    "w3.interactive_clearing": "interactive_clearing",
    "w4.nonlinear_3d": "nonlinear_optimisation_3d",
    "w4.tools_comparison": "modelling_tools_comparison",
    "w6.strong_duality": "strong_duality",
    "w6.weak_duality": "weak_duality",
    "w6.duality_theorems": "duality_theorems",
    "w7.generator_setup": "dispatch_generator_setup",
    "w7.comparison_results": "dispatch_comparison",
    "w7.detailed_analysis": "dispatch_detailed_analysis",
    "w7.individual_generators": "dispatch_individual_generators",
    "w7.pareto": "dispatch_pareto_frontier",
    "w8.market_setup": "auction_market_setup",
    "w8.network_topology": "auction_network_topology",
    "w8.market_results": "auction_market_results",
    "w8.dc_opf_results": "dc_opf_results",
    "w8.market_vs_opf": "auction_vs_dc_opf",
    "w8.theory": "power_flow_theory",
}


def main(dry_run: bool) -> None:
    engine = db.get_engine()
    with engine.begin() as conn:
        present = {r[0] for r in conn.execute(select(db.experiment.c.experiment_id))}

        collisions = [old for old, new in RENAMES.items()
                      if old in present and new in present]
        if collisions:
            raise SystemExit(
                "ABORT: both old and new ids present for: "
                + ", ".join(sorted(collisions))
                + "\nThe new code booted before this migration ran. Resolve by hand."
            )

        renamed = 0
        for old, new in RENAMES.items():
            if old not in present:
                continue
            if not dry_run:
                conn.execute(update(db.experiment)
                             .where(db.experiment.c.experiment_id == old)
                             .values(experiment_id=new))
                conn.execute(update(db.event)
                             .where(db.event.c.experiment_id == old)
                             .values(experiment_id=new))
            print(f"  {old} -> {new}")
            renamed += 1

        unknown = sorted(present - set(RENAMES) - set(RENAMES.values()))
        if unknown:
            print("left alone (not in the rename map): " + ", ".join(unknown))

        verb = "would rename" if dry_run else "renamed"
        print(f"{verb} {renamed} experiment ids")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
```

(`hub/db.py:75` defines `get_engine()`, `hub/db.py:31` the `experiment` table and `:51` the `event` table — the script uses all three as written.)

- [ ] **Step 10: Dry-run the migration against the live database**

Run: `.venv/bin/python scripts/migrate_experiment_ids.py --dry-run`
Expected: 25 `old -> new` lines and "would rename 25 experiment ids". If it aborts on collisions, stop — the new code has already booted against this database.

- [ ] **Step 11: Run the migration for real**

Run: `.venv/bin/python scripts/migrate_experiment_ids.py`
Expected: "renamed 25 experiment ids".

**Do not open the app between this step and the end of Task 11** — the old code's `reconcile` would orphan every renamed row and re-insert the old ids.

- [ ] **Step 12: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. Failures here are in `tests/test_pages_experiment.py` or `tests/test_admin.py` referencing old ids or removed `Experiment` fields — fix them to the new names.

- [ ] **Step 13: Commit**

```bash
git rm catalogue.yaml
git add hub/catalogue.py hub/runner.py hub/db.py scripts/migrate_experiment_ids.py tests/
git commit -m "refactor: render experiments as standalone modules, drop catalogue.yaml"
```

---

### Task 11: Remove the vendoring machinery

**Files:**
- Delete: `sources/` (all six), `scripts/sync_sources.py`, `scripts/capture_baseline.py`, `hub/tabsurgery.py`, `tests/test_sources_intact.py`, `tests/test_tabsurgery.py`
- Modify: `README.md`

- [ ] **Step 1: Confirm nothing still references them**

Run: `grep -rnE "tabsurgery|sync_sources|sources/|catalogue\.yaml" --include="*.py" --include="*.md" --include="*.toml" . | grep -v "^./docs/superpowers/" | grep -v "^./.venv"`
Expected: no hits outside the spec and plan documents. Fix any that appear before deleting.

- [ ] **Step 2: Delete**

```bash
git rm -r sources scripts/sync_sources.py scripts/capture_baseline.py \
        hub/tabsurgery.py tests/test_sources_intact.py tests/test_tabsurgery.py
```

`tests/baseline_render.json` stays: it is the record of what the site rendered before the split, and `tests/test_extraction_faithful.py` still checks against it.

- [ ] **Step 3: Rewrite the README**

Replace the "The one rule: `sources/` is vendored verbatim" section and the "How isolation works instead" section with a description of the new layout: experiments are modules in `experiments/`, one per experiment, each exposing `render()`; shared page bodies live in `experiments/_kit/`; the id is the filename stem and is also the database key, so renaming a file requires a migration; adding an experiment means dropping a new file in `experiments/` and assigning it to a topic in the admin panel. Update the architecture file list (`runner.py`, `catalogue.py` descriptions) and delete the `sync_sources.py` workflow block.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove vendoring machinery now that the hub owns the experiments"
```

---

### Task 12: Verify in the running app, then deploy

- [ ] **Step 1: Boot the app**

Run: `.venv/bin/python -m streamlit run app.py`
Expected: home page renders 25 experiments across the topics you configured, with the titles and ordering intact — that is the migration proving itself.

- [ ] **Step 2: Open one experiment from each former week** (2, 3, 4, 6, 7, 8) and confirm each renders as before, without the duplicated dashboard branding in the sidebar.

- [ ] **Step 3: Confirm shared state still works**

Open a dispatch experiment, change a generator parameter, then open another dispatch experiment. Expected: the change persists (`STATE_GROUP = "dispatch"`). Then open a week-2 experiment and return: state is cleared, as before.

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Notes for the implementer

- **Extraction failures are usually dynamic lookups.** `closure()` follows `ast.Name` references. If an experiment renders less than its baseline, look for a helper called through a dict of functions or a `globals()` lookup, and copy it in by hand.
- **Do not fix bugs you find in the extracted code.** The known demand-curve step bug at `sources/week2_consumer_supplier.py:393-395` is deliberately carried over unchanged so the baseline check passes. Fix it after the split, as its own commit, in `experiments/market_equilibrium.py`.
- **Weeks 7 and 8 are slow.** Their tests run real cvxpy/networkx solves; `default_timeout=180` is there for a reason. A test run of the full suite after Task 9 takes several minutes.
