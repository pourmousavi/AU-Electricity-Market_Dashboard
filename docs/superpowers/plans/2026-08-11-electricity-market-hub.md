# Electricity Market Dashboard Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collate six standalone Streamlit teaching dashboards into one free-hosted site exposing 25 individually-assignable, individually-toggleable experiments, with a live admin panel and anonymous usage analytics.

**Architecture:** Six vendored source files are executed unmodified by a rendering shim with two isolation modes — `pin_selectbox` (monkeypatch the module's one nav dropdown) and `pin_tab` (in-memory AST transform that blanks unselected `with tabN:` bodies). A `catalogue.yaml` describes *how to render* each experiment; a Neon Postgres database describes *how to present* it (topic, title, order, enabled) and is edited live from an admin panel. Routing is query-parameter based in a single `app.py`.

**Tech Stack:** Python 3.12, Streamlit ≥1.40, SQLAlchemy 2 Core + `psycopg[binary]` against Neon Postgres, PyYAML, pytest with `streamlit.testing.v1.AppTest`. Hosting: Streamlit Community Cloud.

**Spec:** `docs/superpowers/specs/2026-08-11-electricity-market-hub-design.md`

## Global Constraints

- **The six files in `sources/` are never edited.** Not reformatted, not linted, not fixed. Every behaviour change is achieved from outside. Any task that finds itself wanting to edit a source file has misunderstood and must stop.
- Python 3.12. Streamlit `>=1.40,<2` (needs `st.context.headers` and `st.query_params`).
- Hub-owned `st.session_state` keys are **always** prefixed `_hub.` — nothing else may use that prefix, and hub keys are never cleared by state isolation.
- Raw IP addresses are never written to the database, logged, or displayed. Only salted SHA-256 hashes.
- Secrets (`neon.dsn`, `admin.password`, `analytics.ip_salt`) live in `.streamlit/secrets.toml`, which is gitignored and never committed.
- Global Streamlit theme stays **light** (`.streamlit/config.toml`). Dark styling is injected per-page and must never apply to an experiment's body.
- Experiment ids are the stable contract between `catalogue.yaml` and the database. Never renumber or rename an existing id.
- Commit after every task.

---

### Task 1: Repository scaffold and vendored sources

**Files:**
- Create: `.gitignore`, `requirements.txt`, `.streamlit/config.toml`, `README.md`
- Create: `sources/week2_consumer_supplier.py`, `sources/week3_pricing_market_power.py`, `sources/week4_optimisation_tools.py`, `sources/week6_duality.py`, `sources/week7_ed_viu.py`, `sources/week8_pf_auction.py` (downloaded verbatim)
- Create: `scripts/sync_sources.py`
- Test: `tests/test_sources_intact.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/sync_sources.py` exposes `SOURCES: dict[str, tuple[str, str]]` mapping local filename → `(github_repo, upstream_path)`, and `sync(dry_run: bool = False) -> list[str]` returning the list of filenames that changed.

- [ ] **Step 1: Create the directory skeleton and gitignore**

```bash
cd "/Users/a1226603/Documents/Electricity Market Course"
mkdir -p hub sources scripts tests .streamlit docs
cat > .gitignore <<'EOF'
__pycache__/
*.pyc
.venv/
venv/
.streamlit/secrets.toml
.pytest_cache/
.DS_Store
EOF
```

- [ ] **Step 2: Download the six source files verbatim**

```bash
cd "/Users/a1226603/Documents/Electricity Market Course"
dl() { gh api "repos/pourmousavi/$1/contents/$2" -H "Accept: application/vnd.github.raw" > "sources/$3"; }
dl Electricity-Market-Course---Consumer-Supplier-Model-Elasticity-and-Equilibrium Dashboard_Week2.py week2_consumer_supplier.py
dl Electricity-Market-Course---Pricing-marketPower-profitCostRecovery-bidding    Dashboard_Week3.py week3_pricing_market_power.py
dl Electricity-Market-Course---Basic-Def-Optimisation-Tools-Comparison           Dashboard_Week4.py week4_optimisation_tools.py
dl Electricity-Market-Course---Duality-Theory                                    Dashboard_Week6.py week6_duality.py
dl Electricity-Market-Course---ED-VIU                                            Dashboard-week7.py week7_ed_viu.py
dl Electricity-Market-Course---PF-double-sided-auction                           Dashboard-Week8.py week8_pf_auction.py
wc -l sources/*.py
```

Expected: 2002, 2064, 1221, 544, 1698, 2715 lines respectively.

- [ ] **Step 3: Write the sync script**

Create `scripts/sync_sources.py`:

```python
"""Re-pull the six vendored dashboards from their upstream repos.

The vendored files under sources/ are never edited by hand. This script is the
only sanctioned way to change them. Run the smoke test afterwards.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES: dict[str, tuple[str, str]] = {
    "week2_consumer_supplier.py": (
        "Electricity-Market-Course---Consumer-Supplier-Model-Elasticity-and-Equilibrium",
        "Dashboard_Week2.py",
    ),
    "week3_pricing_market_power.py": (
        "Electricity-Market-Course---Pricing-marketPower-profitCostRecovery-bidding",
        "Dashboard_Week3.py",
    ),
    "week4_optimisation_tools.py": (
        "Electricity-Market-Course---Basic-Def-Optimisation-Tools-Comparison",
        "Dashboard_Week4.py",
    ),
    "week6_duality.py": (
        "Electricity-Market-Course---Duality-Theory",
        "Dashboard_Week6.py",
    ),
    "week7_ed_viu.py": (
        "Electricity-Market-Course---ED-VIU",
        "Dashboard-week7.py",
    ),
    "week8_pf_auction.py": (
        "Electricity-Market-Course---PF-double-sided-auction",
        "Dashboard-Week8.py",
    ),
}


def _fetch(repo: str, path: str) -> bytes:
    return subprocess.run(
        ["gh", "api", f"repos/pourmousavi/{repo}/contents/{path}",
         "-H", "Accept: application/vnd.github.raw"],
        check=True, capture_output=True,
    ).stdout


def sync(dry_run: bool = False) -> list[str]:
    """Download each upstream file; return names whose content changed."""
    changed: list[str] = []
    for local, (repo, path) in SOURCES.items():
        remote = _fetch(repo, path)
        target = ROOT / "sources" / local
        current = target.read_bytes() if target.exists() else b""
        if hashlib.sha256(remote).digest() != hashlib.sha256(current).digest():
            changed.append(local)
            if not dry_run:
                target.write_bytes(remote)
    return changed


if __name__ == "__main__":
    import sys

    dry = "--dry-run" in sys.argv
    changed = sync(dry_run=dry)
    if not changed:
        print("All six sources are up to date.")
    else:
        verb = "would change" if dry else "updated"
        print(f"{verb}: " + ", ".join(changed))
        print("Run: pytest tests/test_experiments_render.py")
```

- [ ] **Step 4: Write the failing test**

Create `tests/test_sources_intact.py`:

```python
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
```

- [ ] **Step 5: Create requirements, Streamlit config and a venv, then run the test**

`requirements.txt`:

```
streamlit>=1.40,<2
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.15.0
scipy>=1.10.0
sympy>=1.12
matplotlib>=3.7.0
cvxpy>=1.4.0
networkx>=3.1
pypsa>=0.35.0
PyYAML>=6.0
SQLAlchemy>=2.0
psycopg[binary]>=3.1
pytest>=8.0
```

`.streamlit/config.toml`:

```toml
[theme]
base = "light"
primaryColor = "#C8102E"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F3F5F9"
textColor = "#111827"

[server]
runOnSave = false
```

Run:

```bash
cd "/Users/a1226603/Documents/Electricity Market Course"
/opt/anaconda3/bin/python -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m pytest tests/test_sources_intact.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt .streamlit/config.toml sources scripts tests
git commit -m "feat: vendor six dashboard sources with sync script and integrity test"
```

---

### Task 2: Deployment spike — verify the client IP header

This task exists to answer the one open question in the spec before anything is built on top of it. It ends with a deployed URL and a recorded fact.

**Files:**
- Create: `app.py` (temporary spike content, replaced in Task 13)
- Create: `docs/deployment-notes.md`

**Interfaces:**
- Produces: a recorded decision in `docs/deployment-notes.md` — either `IP_SOURCE=xff` or `IP_SOURCE=device_id` — consumed by Task 9.

- [ ] **Step 1: Write the spike app**

Create `app.py`:

```python
"""TEMPORARY SPIKE — replaced by the real router in Task 13.

Purpose: determine whether Streamlit Community Cloud forwards the client IP
in a request header we can read. See docs/deployment-notes.md.
"""
import streamlit as st

st.set_page_config(page_title="Header spike", layout="wide")
st.title("Request header spike")

headers = dict(st.context.headers)
st.write("Total headers:", len(headers))
st.json({k: v for k, v in headers.items()})

for candidate in ("X-Forwarded-For", "x-forwarded-for", "X-Real-Ip", "x-real-ip"):
    if candidate in headers:
        st.success(f"FOUND {candidate} = {headers[candidate]}")
        break
else:
    st.error("No forwarding header present — fall back to a device id.")
```

- [ ] **Step 2: Verify it runs locally**

Run: `.venv/bin/streamlit run app.py --server.headless true --server.port 8599`
Expected: starts without error; visiting `http://localhost:8599` shows a header list. Stop it with Ctrl-C. Locally `X-Forwarded-For` will usually be absent — that is expected and proves nothing. The deployed check is the real one.

- [ ] **Step 3: Commit and push, then deploy (human step)**

```bash
git add app.py
git commit -m "chore: add header spike to verify client IP availability"
git remote add origin https://github.com/pourmousavi/AU-Electricity-Market_Dashboard.git
git push -u origin main
```

Then, in a browser:
1. Go to `https://share.streamlit.io`, sign in with GitHub, grant access to private repositories.
2. Deploy: repo `pourmousavi/AU-Electricity-Market_Dashboard`, branch `main`, main file `app.py`.
3. Choose the subdomain, e.g. `au-electricity-market`.
4. Open the deployed URL and read the output.

- [ ] **Step 4: Record the answer**

Create `docs/deployment-notes.md` with the observed result, e.g.:

```markdown
# Deployment notes

## Client IP availability (spike, Task 2)

Deployed URL: https://au-electricity-market.streamlit.app
Date checked: <date>

Result: <X-Forwarded-For present, value shape "1.2.3.4, 10.0.0.1"> | <no forwarding header>

**Decision: IP_SOURCE=xff** (or **IP_SOURCE=device_id**)

Consequence for the admin panel: the unique-visitor metric is labelled
"Unique IPs" (xff) or "Unique devices" (device_id). Task 9 and Task 16 must
match this decision.
```

- [ ] **Step 5: Commit**

```bash
git add docs/deployment-notes.md
git commit -m "docs: record client IP availability decision from deployment spike"
```

---

### Task 3: Catalogue loader

**Files:**
- Create: `catalogue.yaml`
- Create: `hub/__init__.py` (empty), `hub/catalogue.py`
- Test: `tests/test_catalogue.py`

**Interfaces:**
- Consumes: `sources/*.py` from Task 1.
- Produces:
  - `hub.catalogue.Experiment` — frozen dataclass with fields `id: str`, `source_key: str`, `source_path: Path`, `mode: str`, `selector: str`, `entry: str`.
  - `hub.catalogue.load_catalogue(path: Path | None = None) -> dict[str, Experiment]` — ordered by file order, keyed by id.
  - `hub.catalogue.CatalogueError(Exception)`.

- [ ] **Step 1: Write `catalogue.yaml` with all 25 experiments**

```yaml
# HOW to render each experiment. Presentation (topic, title, order, enabled)
# lives in the database and is edited in the admin panel — not here.
sources:
  week2: sources/week2_consumer_supplier.py
  week3: sources/week3_pricing_market_power.py
  week4: sources/week4_optimisation_tools.py
  week6: sources/week6_duality.py
  week7: sources/week7_ed_viu.py
  week8: sources/week8_pf_auction.py

experiments:
  - {id: w2.consumer_model,       source: week2, mode: pin_selectbox, selector: "Consumer Model"}
  - {id: w2.consumer_elasticity,  source: week2, mode: pin_selectbox, selector: "Consumer Elasticity"}
  - {id: w2.supplier_model,       source: week2, mode: pin_selectbox, selector: "Supplier Model"}
  - {id: w2.supplier_elasticity,  source: week2, mode: pin_selectbox, selector: "Supplier Elasticity"}
  - {id: w2.market_equilibrium,   source: week2, mode: pin_selectbox, selector: "Market Equilibrium"}

  - {id: w3.pool_pricing,         source: week3, mode: pin_selectbox, selector: "Pool Market Pricing"}
  - {id: w3.market_power,         source: week3, mode: pin_selectbox, selector: "Market Power Analysis"}
  - {id: w3.profit_cost_recovery, source: week3, mode: pin_selectbox, selector: "Profit & Cost Recovery"}
  - {id: w3.interactive_clearing, source: week3, mode: pin_selectbox, selector: "Interactive Market Clearing"}

  - {id: w4.nonlinear_3d,         source: week4, mode: pin_selectbox, selector: "3D Nonlinear Optimization"}
  - {id: w4.tools_comparison,     source: week4, mode: pin_selectbox, selector: "Modelling Tools Comparison"}

  - {id: w6.strong_duality,       source: week6, mode: pin_tab, entry: module, selector: "Strong Duality"}
  - {id: w6.weak_duality,         source: week6, mode: pin_tab, entry: module, selector: "Weak Duality Cases"}
  - {id: w6.duality_theorems,     source: week6, mode: pin_tab, entry: module, selector: "Duality Theorems"}

  - {id: w7.generator_setup,      source: week7, mode: pin_tab, entry: main, selector: "🏭 Generator Setup"}
  - {id: w7.comparison_results,   source: week7, mode: pin_tab, entry: main, selector: "📊 Comparison Results"}
  - {id: w7.detailed_analysis,    source: week7, mode: pin_tab, entry: main, selector: "🔍 Detailed Analysis"}
  - {id: w7.individual_generators, source: week7, mode: pin_tab, entry: main, selector: "📈 Individual Generators"}
  - {id: w7.pareto,               source: week7, mode: pin_tab, entry: main, selector: "🎯 Pareto Frontier"}

  - {id: w8.market_setup,         source: week8, mode: pin_tab, entry: main, selector: "🏪 Market Setup"}
  - {id: w8.network_topology,     source: week8, mode: pin_tab, entry: main, selector: "🔌 Network Topology"}
  - {id: w8.market_results,       source: week8, mode: pin_tab, entry: main, selector: "📈 Market Results"}
  - {id: w8.dc_opf_results,       source: week8, mode: pin_tab, entry: main, selector: "⚡ DC OPF Results"}
  - {id: w8.market_vs_opf,        source: week8, mode: pin_tab, entry: main, selector: "🔋 Market vs DC OPF"}
  - {id: w8.theory,               source: week8, mode: pin_tab, entry: main, selector: "📚 Theory & Concepts"}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_catalogue.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_catalogue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.catalogue'`

- [ ] **Step 4: Implement the loader**

Create `hub/__init__.py` (empty file) and `hub/catalogue.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_catalogue.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add catalogue.yaml hub/__init__.py hub/catalogue.py tests/test_catalogue.py
git commit -m "feat: add catalogue loader with validation for 25 experiments"
```

---

### Task 4: AST tab transform

The riskiest mechanism, built and tested in isolation before any Streamlit involvement.

**Files:**
- Create: `hub/tabsurgery.py`
- Test: `tests/test_tabsurgery.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hub.tabsurgery.TabSurgeryError(Exception)`.
  - `hub.tabsurgery.select_tab(source: str, selector: str) -> tuple[ast.Module, int]` — returns the transformed tree and the zero-based index of the selected tab.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tabsurgery.py`:

```python
import ast
from pathlib import Path

import pytest

from hub.tabsurgery import TabSurgeryError, select_tab

ROOT = Path(__file__).resolve().parent.parent

FIXTURE = '''
import streamlit as st
tab1, tab2, tab3 = st.tabs(["Alpha", "Beta", "Gamma"])
with tab1:
    kept_alpha = 1
with tab2:
    kept_beta = 2
with tab3:
    kept_gamma = 3
'''


def _body_of(tree: ast.Module, name: str) -> list[ast.stmt]:
    for node in ast.walk(tree):
        if (isinstance(node, ast.With) and len(node.items) == 1
                and isinstance(node.items[0].context_expr, ast.Name)
                and node.items[0].context_expr.id == name):
            return node.body
    raise AssertionError(f"no with-block for {name}")


def test_returns_selected_index() -> None:
    _, idx = select_tab(FIXTURE, "Beta")
    assert idx == 1


def test_selected_body_is_preserved() -> None:
    tree, _ = select_tab(FIXTURE, "Beta")
    assert not isinstance(_body_of(tree, "tab2")[0], ast.Pass)


def test_unselected_bodies_are_blanked() -> None:
    tree, _ = select_tab(FIXTURE, "Beta")
    for name in ("tab1", "tab3"):
        body = _body_of(tree, name)
        assert len(body) == 1 and isinstance(body[0], ast.Pass)


def test_transformed_tree_still_compiles() -> None:
    tree, _ = select_tab(FIXTURE, "Gamma")
    compile(tree, "<test>", "exec")


def test_unselected_code_does_not_execute() -> None:
    """The point of the whole exercise: blanked tabs never run."""
    tree, idx = select_tab(FIXTURE, "Gamma")
    import contextlib
    import streamlit as st

    original = st.tabs
    st.tabs = lambda labels, *a, **k: [contextlib.nullcontext()] * len(labels)
    try:
        namespace: dict = {}
        exec(compile(tree, "<test>", "exec"), namespace)
    finally:
        st.tabs = original

    assert "kept_gamma" in namespace
    assert "kept_alpha" not in namespace
    assert "kept_beta" not in namespace


def test_rejects_unknown_selector() -> None:
    with pytest.raises(TabSurgeryError, match="no tab labelled"):
        select_tab(FIXTURE, "Delta")


def test_rejects_source_without_tabs() -> None:
    with pytest.raises(TabSurgeryError, match="exactly one"):
        select_tab("x = 1\n", "Alpha")


@pytest.mark.parametrize(
    "filename,selector,expected_index",
    [
        ("week6_duality.py", "Strong Duality", 0),
        ("week6_duality.py", "Duality Theorems", 2),
        ("week7_ed_viu.py", "🎯 Pareto Frontier", 4),
        ("week8_pf_auction.py", "📚 Theory & Concepts", 5),
        ("week8_pf_auction.py", "🏪 Market Setup", 0),
    ],
)
def test_works_on_real_sources(filename: str, selector: str, expected_index: int) -> None:
    source = (ROOT / "sources" / filename).read_text(encoding="utf-8")
    tree, idx = select_tab(source, selector)
    assert idx == expected_index
    compile(tree, filename, "exec")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tabsurgery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.tabsurgery'`

- [ ] **Step 3: Implement the transform**

Create `hub/tabsurgery.py`:

```python
"""In-memory AST surgery that isolates one tab of a vendored dashboard.

The vendored source on disk is never modified. We parse it, replace the body of
every `with tabN:` block that is not the selected one with `pass`, and hand the
transformed tree back to the runner. Unselected tabs therefore never execute —
no wasted solver time, and disabled content is never computed.

This is deliberately strict: if a source file stops matching the expected
`tab1, tab2 = st.tabs([...])` / `with tabN:` shape, we raise instead of quietly
rendering the wrong thing.
"""
from __future__ import annotations

import ast


class TabSurgeryError(Exception):
    """The source does not match the tab pattern we can transform."""


def _find_tabs_assignment(tree: ast.Module) -> ast.Assign:
    assigns = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "tabs"
    ]
    if len(assigns) != 1:
        raise TabSurgeryError(
            f"expected exactly one `... = st.tabs([...])` assignment, found {len(assigns)}"
        )
    return assigns[0]


def select_tab(source: str, selector: str) -> tuple[ast.Module, int]:
    """Blank every tab body except the one labelled `selector`.

    Returns the transformed tree and the selected tab's zero-based index.
    """
    tree = ast.parse(source)
    assign = _find_tabs_assignment(tree)

    target = assign.targets[0]
    if not isinstance(target, ast.Tuple):
        raise TabSurgeryError("st.tabs result is not unpacked into a tuple of names")
    if not all(isinstance(el, ast.Name) for el in target.elts):
        raise TabSurgeryError("st.tabs targets are not all plain names")
    names = [el.id for el in target.elts]

    if not assign.value.args:
        raise TabSurgeryError("st.tabs called without a label list")
    label_node = assign.value.args[0]
    if not isinstance(label_node, ast.List):
        raise TabSurgeryError("st.tabs labels are not a literal list")
    if not all(isinstance(el, ast.Constant) and isinstance(el.value, str)
               for el in label_node.elts):
        raise TabSurgeryError("st.tabs labels are not all literal strings")
    labels = [el.value for el in label_node.elts]

    if len(names) != len(labels):
        raise TabSurgeryError(
            f"{len(names)} tab variables but {len(labels)} labels"
        )
    if selector not in labels:
        raise TabSurgeryError(f"no tab labelled {selector!r}; available: {labels}")

    index = labels.index(selector)
    keep = names[index]

    for node in ast.walk(tree):
        if (isinstance(node, ast.With) and len(node.items) == 1
                and isinstance(node.items[0].context_expr, ast.Name)):
            name = node.items[0].context_expr.id
            if name in names and name != keep:
                node.body = [ast.Pass()]

    ast.fix_missing_locations(tree)
    return tree, index
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_tabsurgery.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/tabsurgery.py tests/test_tabsurgery.py
git commit -m "feat: add AST tab isolation with strict pattern validation"
```

---

### Task 5: Session state isolation

**Files:**
- Create: `hub/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hub.state.HUB_PREFIX: str` = `"_hub."`.
  - `hub.state.isolate(session_state, source_key: str) -> bool` — clears all non-hub keys when `source_key` differs from the previously active source; returns `True` if it cleared. Takes the state mapping as an argument so it is testable with a plain dict.

- [ ] **Step 1: Write the failing test**

Create `tests/test_state.py`:

```python
from hub.state import ACTIVE_SOURCE_KEY, HUB_PREFIX, isolate


def test_first_call_sets_active_source_and_clears_nothing() -> None:
    state = {"generators": [1, 2]}
    assert isolate(state, "week7") is False
    assert state["generators"] == [1, 2]
    assert state[ACTIVE_SOURCE_KEY] == "week7"


def test_same_source_preserves_state() -> None:
    state = {ACTIVE_SOURCE_KEY: "week7", "generators": [1, 2]}
    assert isolate(state, "week7") is False
    assert state["generators"] == [1, 2]


def test_different_source_clears_foreign_keys() -> None:
    state = {ACTIVE_SOURCE_KEY: "week7", "generators": [1, 2], "demand_bids": []}
    assert isolate(state, "week8") is True
    assert "generators" not in state
    assert "demand_bids" not in state
    assert state[ACTIVE_SOURCE_KEY] == "week8"


def test_hub_keys_survive_a_switch() -> None:
    state = {
        ACTIVE_SOURCE_KEY: "week7",
        f"{HUB_PREFIX}events": ["a"],
        f"{HUB_PREFIX}session_id": "abc",
        "generators": [1],
    }
    isolate(state, "week8")
    assert state[f"{HUB_PREFIX}events"] == ["a"]
    assert state[f"{HUB_PREFIX}session_id"] == "abc"
    assert "generators" not in state
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.state'`

- [ ] **Step 3: Implement**

Create `hub/state.py`:

```python
"""Keeps vendored modules from corrupting each other's session state.

Three key names collide across the six dashboards (`generators`,
`supply_bids`, `demand_bids`) with different shapes. Since every experiment
shares one Streamlit session, switching from a Week 7 experiment to a Week 8 one
would hand Week 8 a Week 7 list and crash it.

Rule: when the active source module changes, drop every key the vendored code
could own. Hub-owned keys are prefixed and always survive. Switching between two
experiments of the *same* module preserves state, matching how those dashboards
behave standalone.
"""
from __future__ import annotations

from typing import MutableMapping

HUB_PREFIX = "_hub."
ACTIVE_SOURCE_KEY = f"{HUB_PREFIX}active_source"


def isolate(session_state: MutableMapping, source_key: str) -> bool:
    """Clear foreign module state if the active source changed.

    Returns True if keys were cleared.
    """
    previous = session_state.get(ACTIVE_SOURCE_KEY)
    cleared = False

    if previous is not None and previous != source_key:
        foreign = [k for k in list(session_state) if not str(k).startswith(HUB_PREFIX)]
        for key in foreign:
            del session_state[key]
        cleared = True

    session_state[ACTIVE_SOURCE_KEY] = source_key
    return cleared
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_state.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/state.py tests/test_state.py
git commit -m "feat: isolate session state across vendored modules"
```

---

### Task 6: The runner

**Files:**
- Create: `hub/runner.py`
- Test: `tests/test_runner_units.py`

**Interfaces:**
- Consumes: `hub.catalogue.Experiment`, `hub.tabsurgery.select_tab`, `hub.state.isolate`.
- Produces:
  - `hub.runner.ExperimentRenderError(Exception)`.
  - `hub.runner.render_experiment(exp: Experiment) -> None` — renders one experiment into the current Streamlit context.
  - `hub.runner.prepare(source_path: str, mode: str, selector: str) -> tuple[CodeType, int]` — cached compile step, exposed for testing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner_units.py`:

```python
"""Unit tests for the runner's patching primitives.

Full end-to-end rendering of all 25 experiments is Task 7.
"""
import contextlib

import pytest
import streamlit as st

from hub.catalogue import load_catalogue
from hub.runner import ExperimentRenderError, _no_page_config, _pinned_selectbox, _pinned_tabs, prepare


def test_page_config_is_noop_inside_context_and_restored_after() -> None:
    original = st.set_page_config
    with _no_page_config():
        assert st.set_page_config is not original
        st.set_page_config(page_title="ignored")  # must not raise
    assert st.set_page_config is original


def test_pinned_selectbox_returns_selector_on_first_call_only() -> None:
    original = st.sidebar.selectbox
    calls = []
    with _pinned_selectbox("Supplier Model"):
        first = st.sidebar.selectbox("Pick", ["Consumer Model", "Supplier Model"])
        calls.append(first)
    assert calls == ["Supplier Model"]
    assert st.sidebar.selectbox is original


def test_pinned_selectbox_rejects_absent_option() -> None:
    with pytest.raises(ExperimentRenderError, match="not among the options"):
        with _pinned_selectbox("Nonexistent"):
            st.sidebar.selectbox("Pick", ["Consumer Model"])


def test_pinned_tabs_returns_nullcontext_for_unselected() -> None:
    with _pinned_tabs(1, "Beta"):
        tabs = st.tabs(["Alpha", "Beta", "Gamma"])
    assert len(tabs) == 3
    assert isinstance(tabs[0], contextlib.nullcontext)
    assert isinstance(tabs[2], contextlib.nullcontext)
    assert not isinstance(tabs[1], contextlib.nullcontext)


def test_prepare_returns_index_for_pin_tab() -> None:
    exp = load_catalogue()["w7.pareto"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == 4


def test_prepare_returns_minus_one_for_pin_selectbox() -> None:
    exp = load_catalogue()["w2.supplier_model"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == -1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_runner_units.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.runner'`

- [ ] **Step 3: Implement the runner**

Create `hub/runner.py`:

```python
"""Executes one experiment out of a vendored dashboard, unmodified.

Two isolation modes, both of which guarantee that only the selected
experiment's code runs:

  pin_selectbox — Weeks 2/3/4 each call `st.sidebar.selectbox` exactly once at
    module level and dispatch on the result with `if page == ...`. We make that
    one call return the experiment we want, then execute the file. Exactly one
    branch runs.

  pin_tab — Weeks 6/7/8 build their content inside `with tabN:` blocks whose
    bodies are partly inline code, so calling render functions is not enough.
    We blank the unselected bodies in the AST (see hub.tabsurgery) and patch
    st.tabs to draw a single tab.

Never edit anything under sources/.
"""
from __future__ import annotations

import contextlib
import types
from pathlib import Path
from types import CodeType

import streamlit as st

from hub.catalogue import Experiment
from hub.state import isolate
from hub.tabsurgery import TabSurgeryError, select_tab


class ExperimentRenderError(Exception):
    """An experiment could not be rendered from its source."""


@contextlib.contextmanager
def _no_page_config():
    """Vendored modules all call st.set_page_config; only the hub may."""
    original = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None
    try:
        yield
    finally:
        st.set_page_config = original


@contextlib.contextmanager
def _pinned_selectbox(selector: str):
    """Force the module's single nav dropdown to return `selector`.

    Only the first call is intercepted — inner `st.selectbox` calls in the main
    area are untouched, and any later sidebar dropdown behaves normally.
    """
    original = st.sidebar.selectbox
    used = {"value": False}

    def shim(label, options, *args, **kwargs):
        if used["value"]:
            return original(label, options, *args, **kwargs)
        used["value"] = True
        if selector not in list(options):
            raise ExperimentRenderError(
                f"{selector!r} is not among the options {list(options)!r}"
            )
        return selector

    st.sidebar.selectbox = shim
    try:
        yield
    finally:
        st.sidebar.selectbox = original


@contextlib.contextmanager
def _pinned_tabs(index: int, selector: str):
    """Draw a single tab, and hand back nullcontexts for the blanked ones."""
    original = st.tabs

    def shim(labels, *args, **kwargs):
        real = original([selector], *args, **kwargs)[0]
        out: list = [contextlib.nullcontext() for _ in labels]
        out[index] = real
        return out

    st.tabs = shim
    try:
        yield
    finally:
        st.tabs = original


@st.cache_resource(show_spinner=False)
def prepare(source_path: str, mode: str, selector: str) -> tuple[CodeType, int]:
    """Compile a source for one experiment. Cached per (file, mode, selector).

    Returns the code object and the selected tab index (-1 for pin_selectbox).
    """
    path = Path(source_path)
    source = path.read_text(encoding="utf-8")

    if mode == "pin_selectbox":
        return compile(source, str(path), "exec"), -1

    if mode == "pin_tab":
        try:
            tree, index = select_tab(source, selector)
        except TabSurgeryError as exc:
            raise ExperimentRenderError(f"{path.name}: {exc}") from exc
        return compile(tree, str(path), "exec"), index

    raise ExperimentRenderError(f"unknown mode {mode!r}")


def render_experiment(exp: Experiment) -> None:
    """Render one experiment into the current Streamlit context."""
    isolate(st.session_state, exp.source_key)
    code, index = prepare(str(exp.source_path), exp.mode, exp.selector)

    module = types.ModuleType("_hub_vendored")
    module.__file__ = str(exp.source_path)
    module.__dict__["__name__"] = "_hub_vendored"  # keeps __main__ guards shut

    with _no_page_config():
        if exp.mode == "pin_selectbox":
            with _pinned_selectbox(exp.selector):
                exec(code, module.__dict__)
        else:
            with _pinned_tabs(index, exp.selector):
                exec(code, module.__dict__)
                if exp.entry == "main":
                    entry = module.__dict__.get("main")
                    if not callable(entry):
                        raise ExperimentRenderError(
                            f"{exp.id}: source has no callable main()"
                        )
                    entry()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_runner_units.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/runner.py tests/test_runner_units.py
git commit -m "feat: add experiment runner with selectbox and tab isolation"
```

---

### Task 7: Full render smoke test over all 25 experiments

The regression net for every later change and for every `sync_sources.py` run.

**Files:**
- Create: `tests/test_experiments_render.py`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: `hub.catalogue.load_catalogue`, `hub.runner.render_experiment`.
- Produces: nothing consumed by later tasks; this is a gate.

- [ ] **Step 1: Write the test**

Create `tests/test_experiments_render.py`:

```python
"""Every experiment must render without raising.

This is the check that catches a vendored dashboard being restructured
upstream. Run it after every scripts/sync_sources.py.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hub.catalogue import load_catalogue

ROOT = Path(__file__).resolve().parent.parent
ALL_IDS = sorted(load_catalogue())


def _harness(exp_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from hub.catalogue import load_catalogue\n"
        "from hub.runner import render_experiment\n"
        f"render_experiment(load_catalogue()[{exp_id!r}])\n"
    )


def test_catalogue_has_expected_size() -> None:
    assert len(ALL_IDS) == 25


@pytest.mark.parametrize("exp_id", ALL_IDS)
def test_experiment_renders_without_exception(exp_id: str) -> None:
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    assert not app.exception, (
        f"{exp_id} raised: "
        + "; ".join(e.message for e in app.exception)
    )


@pytest.mark.parametrize("exp_id", ALL_IDS)
def test_experiment_produces_output(exp_id: str) -> None:
    """A silent success is a failure — every experiment must render something."""
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    produced = len(app.markdown) + len(app.header) + len(app.subheader) + len(app.title)
    assert produced > 0, f"{exp_id} rendered no text output at all"
```

- [ ] **Step 2: Add pytest config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 3: Run the smoke test**

Run: `.venv/bin/python -m pytest tests/test_experiments_render.py -v`
Expected: 51 passed. Expect it to take several minutes — Week 8 imports PyPSA.

If an experiment fails, the fix goes in `hub/runner.py` or `hub/tabsurgery.py`. **Do not edit anything under `sources/`.**

- [ ] **Step 4: Commit**

```bash
git add tests/test_experiments_render.py pytest.ini
git commit -m "test: smoke test all 25 experiments render without exception"
```

---

### Task 8: Database layer

**Files:**
- Create: `hub/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `hub.catalogue.Experiment`.
- Produces:
  - `hub.db.metadata`, and tables `topic`, `experiment`, `visitor_session`, `event` (SQLAlchemy Core `Table` objects).
  - `hub.db.get_engine() -> Engine` — cached, reads `st.secrets["neon"]["dsn"]`.
  - `hub.db.bootstrap(engine) -> None` — create tables if absent.
  - `hub.db.reconcile(engine, catalogue: dict[str, Experiment]) -> tuple[int, int]` — returns `(inserted, orphaned)`.
  - `hub.db.seed_initial(engine, catalogue) -> bool` — returns True if it seeded.
  - `hub.db.list_topics(engine, include_disabled: bool) -> list[dict]`
  - `hub.db.list_experiments(engine, topic_id: int | None, include_disabled: bool) -> list[dict]`
  - `hub.db.get_experiment(engine, experiment_id: str) -> dict | None`
  - `hub.db.set_experiment_enabled(engine, experiment_id: str, enabled: bool) -> None`
  - `hub.db.assign_experiment(engine, experiment_id: str, topic_id: int | None, sort_order: int) -> None`
  - `hub.db.update_experiment_text(engine, experiment_id: str, title: str, blurb: str) -> None`
  - `hub.db.upsert_topic(engine, topic_id: int | None, name: str, subtitle: str, unlock_message: str, sort_order: int, enabled: bool) -> int`
  - `hub.db.delete_topic(engine, topic_id: int) -> None`

Experiment rows are dicts with keys: `experiment_id, topic_id, title, blurb, sort_order, enabled, orphaned`.
Topic rows are dicts with keys: `id, name, subtitle, unlock_message, sort_order, enabled`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py`:

```python
import pytest
from sqlalchemy import create_engine

from hub import db
from hub.catalogue import load_catalogue


@pytest.fixture()
def engine():
    """In-memory SQLite. SQLAlchemy Core keeps the DDL portable to Postgres."""
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    return eng


def test_bootstrap_creates_all_tables(engine) -> None:
    from sqlalchemy import inspect

    names = set(inspect(engine).get_table_names())
    assert {"topic", "experiment", "visitor_session", "event"} <= names


def test_seed_creates_six_topics_with_all_experiments_enabled(engine) -> None:
    cat = load_catalogue()
    assert db.seed_initial(engine, cat) is True

    topics = db.list_topics(engine, include_disabled=True)
    assert [t["name"] for t in topics] == [
        "Week 2", "Week 3", "Week 4", "Week 6", "Week 7", "Week 8"
    ]

    rows = db.list_experiments(engine, topic_id=None, include_disabled=True)
    assert len(rows) == 25
    assert all(r["enabled"] for r in rows)
    assert all(r["topic_id"] is not None for r in rows)


def test_seed_is_idempotent(engine) -> None:
    cat = load_catalogue()
    assert db.seed_initial(engine, cat) is True
    assert db.seed_initial(engine, cat) is False
    assert len(db.list_topics(engine, include_disabled=True)) == 6


def test_reconcile_inserts_new_ids_disabled_and_unassigned(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)

    from hub.catalogue import Experiment

    extra = dict(cat)
    extra["w9.brand_new"] = Experiment(
        id="w9.brand_new", source_key="week2",
        source_path=cat["w2.consumer_model"].source_path,
        mode="pin_selectbox", selector="Consumer Model", entry="module",
    )
    inserted, orphaned = db.reconcile(engine, extra)
    assert inserted == 1 and orphaned == 0

    row = db.get_experiment(engine, "w9.brand_new")
    assert row["enabled"] is False
    assert row["topic_id"] is None


def test_reconcile_marks_missing_ids_orphaned_without_deleting(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)

    shrunk = {k: v for k, v in cat.items() if k != "w8.theory"}
    inserted, orphaned = db.reconcile(engine, shrunk)
    assert inserted == 0 and orphaned == 1

    row = db.get_experiment(engine, "w8.theory")
    assert row is not None and row["orphaned"] is True


def test_orphaned_experiments_are_hidden_from_students(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)
    db.reconcile(engine, {k: v for k, v in cat.items() if k != "w8.theory"})

    visible = db.list_experiments(engine, topic_id=None, include_disabled=False)
    assert "w8.theory" not in {r["experiment_id"] for r in visible}


def test_toggle_and_reassign(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)
    week2 = db.list_topics(engine, include_disabled=True)[0]["id"]

    db.set_experiment_enabled(engine, "w8.theory", False)
    assert db.get_experiment(engine, "w8.theory")["enabled"] is False

    db.assign_experiment(engine, "w8.theory", topic_id=week2, sort_order=99)
    row = db.get_experiment(engine, "w8.theory")
    assert row["topic_id"] == week2 and row["sort_order"] == 99


def test_upsert_topic_creates_then_updates(engine) -> None:
    new_id = db.upsert_topic(
        engine, None, "Revision", "Exam prep", "Opens in swotvac", 10, True
    )
    assert isinstance(new_id, int)
    same_id = db.upsert_topic(
        engine, new_id, "Revision Week", "Exam prep", "Opens in swotvac", 10, True
    )
    assert same_id == new_id
    names = [t["name"] for t in db.list_topics(engine, include_disabled=True)]
    assert "Revision Week" in names and "Revision" not in names


def test_update_experiment_text(engine) -> None:
    db.seed_initial(engine, load_catalogue())
    db.update_experiment_text(engine, "w2.consumer_model", "Demand Curves", "Start here.")
    row = db.get_experiment(engine, "w2.consumer_model")
    assert row["title"] == "Demand Curves"
    assert row["blurb"] == "Start here."
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'db' from 'hub'`

- [ ] **Step 3: Implement the database layer**

Create `hub/db.py`:

```python
"""Presentation state: topics, experiment placement, and analytics storage.

SQLAlchemy Core rather than raw SQL so the same DDL runs on Neon Postgres in
production and in-memory SQLite in the tests.
"""
from __future__ import annotations

from typing import Any

import streamlit as st
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table,
    Text, create_engine, delete, func, insert, select, update,
)
from sqlalchemy.engine import Engine

from hub.catalogue import Experiment

metadata = MetaData()

topic = Table(
    "topic", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(120), nullable=False),
    Column("subtitle", Text, nullable=False, default=""),
    Column("unlock_message", Text, nullable=False, default=""),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("enabled", Boolean, nullable=False, default=True),
)

experiment = Table(
    "experiment", metadata,
    Column("experiment_id", String(120), primary_key=True),
    Column("topic_id", Integer, ForeignKey("topic.id"), nullable=True),
    Column("title", String(200), nullable=False),
    Column("blurb", Text, nullable=False, default=""),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("enabled", Boolean, nullable=False, default=False),
    Column("orphaned", Boolean, nullable=False, default=False),
)

visitor_session = Table(
    "visitor_session", metadata,
    Column("id", String(80), primary_key=True),
    Column("ip_hash", String(64), nullable=True),
    Column("user_agent", Text, nullable=True),
    Column("referrer", Text, nullable=True),
    Column("first_seen", DateTime(timezone=True), server_default=func.now()),
)

event = Table(
    "event", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(80), nullable=True),
    Column("ts", DateTime(timezone=True), server_default=func.now()),
    Column("kind", String(40), nullable=False),
    Column("topic_id", Integer, nullable=True),
    Column("experiment_id", String(120), nullable=True),
    Column("dwell_ms", Integer, nullable=True),
)

# Default titles for the initial seed, derived from the catalogue id.
_SEED_TOPICS = ["week2", "week3", "week4", "week6", "week7", "week8"]
_TOPIC_NAMES = {
    "week2": ("Week 2", "Consumer and supplier models, elasticity, equilibrium"),
    "week3": ("Week 3", "Pricing, market power, profit and cost recovery, bidding"),
    "week4": ("Week 4", "Optimisation problems and modelling tool comparison"),
    "week6": ("Week 6", "Linear programming duality"),
    "week7": ("Week 7", "Economic dispatch and value of interrupted use"),
    "week8": ("Week 8", "Power flow and the double-sided auction"),
}


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    """Engine for the configured Neon database."""
    return create_engine(st.secrets["neon"]["dsn"], pool_pre_ping=True)


def bootstrap(engine: Engine) -> None:
    metadata.create_all(engine)


def _default_title(experiment_id: str) -> str:
    tail = experiment_id.split(".", 1)[-1]
    return tail.replace("_", " ").title()


def seed_initial(engine: Engine, catalogue: dict[str, Experiment]) -> bool:
    """Create the six week topics with every experiment assigned and enabled.

    Only runs when the topic table is empty. Returns True if it seeded.
    """
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(topic)).scalar_one() > 0:
            return False

        topic_ids: dict[str, int] = {}
        for order, key in enumerate(_SEED_TOPICS):
            name, subtitle = _TOPIC_NAMES[key]
            result = conn.execute(insert(topic).values(
                name=name, subtitle=subtitle,
                unlock_message="Available after the lecture for this week.",
                sort_order=order, enabled=True,
            ))
            topic_ids[key] = int(result.inserted_primary_key[0])

        per_topic_order: dict[str, int] = {}
        for exp in catalogue.values():
            order = per_topic_order.get(exp.source_key, 0)
            per_topic_order[exp.source_key] = order + 1
            conn.execute(insert(experiment).values(
                experiment_id=exp.id,
                topic_id=topic_ids.get(exp.source_key),
                title=_default_title(exp.id),
                blurb="",
                sort_order=order,
                enabled=True,
                orphaned=False,
            ))
    return True


def reconcile(engine: Engine, catalogue: dict[str, Experiment]) -> tuple[int, int]:
    """Sync DB rows with the catalogue. Returns (inserted, newly orphaned).

    New catalogue ids arrive unassigned and disabled, so nothing reaches
    students until it is deliberately placed. Ids that vanish from the
    catalogue are flagged, never deleted.
    """
    inserted = orphaned = 0
    with engine.begin() as conn:
        known = {r[0] for r in conn.execute(select(experiment.c.experiment_id))}

        for exp_id in catalogue:
            if exp_id not in known:
                conn.execute(insert(experiment).values(
                    experiment_id=exp_id, topic_id=None,
                    title=_default_title(exp_id), blurb="",
                    sort_order=0, enabled=False, orphaned=False,
                ))
                inserted += 1

        for exp_id in known:
            if exp_id not in catalogue:
                result = conn.execute(
                    update(experiment)
                    .where(experiment.c.experiment_id == exp_id,
                           experiment.c.orphaned.is_(False))
                    .values(orphaned=True)
                )
                orphaned += result.rowcount or 0

        # An id that came back is no longer orphaned.
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id.in_(list(catalogue)))
            .values(orphaned=False)
        )
    return inserted, orphaned


def _rows(result) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in result]


def list_topics(engine: Engine, include_disabled: bool) -> list[dict[str, Any]]:
    stmt = select(topic).order_by(topic.c.sort_order, topic.c.id)
    if not include_disabled:
        stmt = stmt.where(topic.c.enabled.is_(True))
    with engine.connect() as conn:
        return _rows(conn.execute(stmt))


def list_experiments(
    engine: Engine, topic_id: int | None, include_disabled: bool
) -> list[dict[str, Any]]:
    """Experiments, optionally scoped to one topic.

    `topic_id=None` means every topic. Orphaned rows are only ever returned
    when include_disabled is True (i.e. to the admin).
    """
    stmt = select(experiment).order_by(experiment.c.sort_order, experiment.c.experiment_id)
    if topic_id is not None:
        stmt = stmt.where(experiment.c.topic_id == topic_id)
    if not include_disabled:
        stmt = stmt.where(
            experiment.c.enabled.is_(True), experiment.c.orphaned.is_(False)
        )
    with engine.connect() as conn:
        return _rows(conn.execute(stmt))


def get_experiment(engine: Engine, experiment_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(experiment).where(experiment.c.experiment_id == experiment_id)
        ).first()
    return dict(row._mapping) if row else None


def set_experiment_enabled(engine: Engine, experiment_id: str, enabled: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(enabled=enabled)
        )


def assign_experiment(
    engine: Engine, experiment_id: str, topic_id: int | None, sort_order: int
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(topic_id=topic_id, sort_order=sort_order)
        )


def update_experiment_text(
    engine: Engine, experiment_id: str, title: str, blurb: str
) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.experiment_id == experiment_id)
            .values(title=title, blurb=blurb)
        )


def upsert_topic(
    engine: Engine, topic_id: int | None, name: str, subtitle: str,
    unlock_message: str, sort_order: int, enabled: bool,
) -> int:
    values = dict(
        name=name, subtitle=subtitle, unlock_message=unlock_message,
        sort_order=sort_order, enabled=enabled,
    )
    with engine.begin() as conn:
        if topic_id is None:
            result = conn.execute(insert(topic).values(**values))
            return int(result.inserted_primary_key[0])
        conn.execute(update(topic).where(topic.c.id == topic_id).values(**values))
        return topic_id


def delete_topic(engine: Engine, topic_id: int) -> None:
    """Remove a topic; its experiments become unassigned rather than vanishing."""
    with engine.begin() as conn:
        conn.execute(
            update(experiment)
            .where(experiment.c.topic_id == topic_id)
            .values(topic_id=None, enabled=False)
        )
        conn.execute(delete(topic).where(topic.c.id == topic_id))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: 9 passed.

- [ ] **Step 5: Create the Neon database (human step)**

1. Go to `https://neon.tech`, sign in with GitHub, create a project named `au-electricity-market`.
2. Copy the connection string. Convert the scheme for SQLAlchemy: `postgresql://...` becomes `postgresql+psycopg://...`.
3. Create `.streamlit/secrets.toml` locally (already gitignored):

```toml
[neon]
dsn = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require"

[admin]
password = "choose-a-strong-password"

[analytics]
ip_salt = "paste-32-random-characters-here"
```

4. Add the same three values in the Streamlit Cloud app's **Settings → Secrets**.

5. Create `.streamlit/secrets.toml.example` — committed, so the shape is documented
   without leaking anything:

```toml
# Copy to .streamlit/secrets.toml and fill in. That file is gitignored.
[neon]
dsn = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require"

[admin]
password = ""

[analytics]
ip_salt = ""
```

- [ ] **Step 6: Commit**

```bash
git add hub/db.py tests/test_db.py .streamlit/secrets.toml.example
git commit -m "feat: add topic/experiment/analytics schema with seed and reconcile"
```

---

### Task 9: Analytics capture

**Files:**
- Create: `hub/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Consumes: `hub.db` tables and `get_engine`.
- Produces:
  - `hub.analytics.hash_ip(ip: str, salt: str) -> str` — salted SHA-256 hex digest.
  - `hub.analytics.extract_client_ip(headers: Mapping[str, str]) -> str | None` — first address in `X-Forwarded-For`, case-insensitive, falls back to `X-Real-Ip`.
  - `hub.analytics.IDENTITY_LABEL: str` — `"Unique IPs"` or `"Unique devices"`, per the Task 2 decision, displayed by the admin panel.
  - `hub.analytics.ensure_session(engine) -> str` — inserts the visitor row once per Streamlit session, returns the session id.
  - `hub.analytics.track(engine, kind: str, topic_id: int | None = None, experiment_id: str | None = None, dwell_ms: int | None = None) -> None` — buffers and flushes.
  - `hub.analytics.flush(engine) -> int` — writes buffered events, returns the number written.
  - `hub.analytics.BUFFER_KEY: str` = `"_hub.events"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analytics.py`:

```python
import pytest
from sqlalchemy import create_engine, func, select

from hub import analytics, db


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    return eng


def test_hash_is_stable_for_same_salt() -> None:
    assert analytics.hash_ip("1.2.3.4", "salt") == analytics.hash_ip("1.2.3.4", "salt")


def test_hash_differs_across_salts() -> None:
    assert analytics.hash_ip("1.2.3.4", "a") != analytics.hash_ip("1.2.3.4", "b")


def test_hash_differs_across_addresses() -> None:
    assert analytics.hash_ip("1.2.3.4", "s") != analytics.hash_ip("1.2.3.5", "s")


def test_hash_is_not_reversible_to_the_input() -> None:
    digest = analytics.hash_ip("203.0.113.9", "s")
    assert "203.0.113.9" not in digest
    assert len(digest) == 64


def test_extract_takes_first_address_of_forwarded_chain() -> None:
    headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1, 10.0.0.2"}
    assert analytics.extract_client_ip(headers) == "203.0.113.9"


def test_extract_is_case_insensitive() -> None:
    assert analytics.extract_client_ip({"x-forwarded-for": "203.0.113.9"}) == "203.0.113.9"


def test_extract_falls_back_to_real_ip() -> None:
    assert analytics.extract_client_ip({"X-Real-Ip": "198.51.100.7"}) == "198.51.100.7"


def test_extract_returns_none_when_absent() -> None:
    assert analytics.extract_client_ip({"User-Agent": "x"}) is None


def test_track_buffers_without_writing(engine) -> None:
    state: dict = {}
    analytics.track(engine, "home_view", state=state, flush_at=5)
    assert len(state[analytics.BUFFER_KEY]) == 1
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.event)).scalar_one() == 0


def test_buffer_flushes_at_threshold(engine) -> None:
    state: dict = {}
    for _ in range(5):
        analytics.track(engine, "home_view", state=state, flush_at=5)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.event)).scalar_one() == 5
    assert state[analytics.BUFFER_KEY] == []


def test_explicit_flush_writes_remainder(engine) -> None:
    state: dict = {}
    analytics.track(engine, "topic_view", topic_id=3, state=state, flush_at=99)
    assert analytics.flush(engine, state=state) == 1
    with engine.connect() as conn:
        row = conn.execute(select(db.event)).first()
    assert row._mapping["kind"] == "topic_view"
    assert row._mapping["topic_id"] == 3


def test_flush_on_empty_buffer_is_a_noop(engine) -> None:
    assert analytics.flush(engine, state={}) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_analytics.py -v`
Expected: FAIL with `ImportError: cannot import name 'analytics' from 'hub'`

- [ ] **Step 3: Implement**

Create `hub/analytics.py`. Set `IDENTITY_LABEL` to match the recorded decision in `docs/deployment-notes.md` from Task 2.

```python
"""Anonymous usage capture.

Raw IP addresses are never stored. We keep a salted SHA-256 hash, which is
enough to count unique visitors and spot repeat visits, and is not reasonably
re-identifiable without the salt (which lives only in deployment secrets).

If the platform does not forward the client IP at all, we fall back to an
anonymous id in the URL query string and count devices instead — and say so, in
the admin panel, rather than mislabelling the number.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Mapping, MutableMapping

import streamlit as st
from sqlalchemy import insert
from sqlalchemy.engine import Engine

from hub import db

BUFFER_KEY = "_hub.events"
SESSION_KEY = "_hub.session_id"
DEVICE_PARAM = "d"
FLUSH_AT = 5

# Set from the Task 2 spike result recorded in docs/deployment-notes.md.
# "Unique IPs" when X-Forwarded-For is available, else "Unique devices".
IDENTITY_LABEL = "Unique IPs"

_FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip")


def hash_ip(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def extract_client_ip(headers: Mapping[str, str]) -> str | None:
    """First address of the forwarding chain, or None."""
    lowered = {str(k).lower(): v for k, v in headers.items()}
    for name in _FORWARD_HEADERS:
        value = lowered.get(name)
        if value:
            return value.split(",")[0].strip() or None
    return None


def _state(state: MutableMapping | None) -> MutableMapping:
    return st.session_state if state is None else state


def ensure_session(engine: Engine, state: MutableMapping | None = None) -> str:
    """Register this browser session once; return its id."""
    store = _state(state)
    existing = store.get(SESSION_KEY)
    if existing:
        return existing

    try:
        headers = dict(st.context.headers)
    except Exception:  # not inside a live Streamlit runtime
        headers = {}

    ip = extract_client_ip(headers)
    if ip is not None:
        session_id = hash_ip(ip, st.secrets["analytics"]["ip_salt"])[:32] + \
            "-" + secrets.token_hex(8)
        ip_hash = hash_ip(ip, st.secrets["analytics"]["ip_salt"])
    else:
        device = st.query_params.get(DEVICE_PARAM)
        if not device:
            device = secrets.token_hex(8)
            st.query_params[DEVICE_PARAM] = device
        session_id = f"{device}-{secrets.token_hex(8)}"
        ip_hash = hash_ip(device, st.secrets["analytics"]["ip_salt"])

    with engine.begin() as conn:
        conn.execute(insert(db.visitor_session).values(
            id=session_id,
            ip_hash=ip_hash,
            user_agent=headers.get("user-agent") or headers.get("User-Agent"),
            referrer=headers.get("referer") or headers.get("Referer"),
        ))

    store[SESSION_KEY] = session_id
    return session_id


def track(
    engine: Engine,
    kind: str,
    topic_id: int | None = None,
    experiment_id: str | None = None,
    dwell_ms: int | None = None,
    state: MutableMapping | None = None,
    flush_at: int = FLUSH_AT,
) -> None:
    """Buffer one event; write the batch once it is worth a round trip."""
    store = _state(state)
    buffer: list[dict[str, Any]] = store.setdefault(BUFFER_KEY, [])
    buffer.append({
        "session_id": store.get(SESSION_KEY),
        "kind": kind,
        "topic_id": topic_id,
        "experiment_id": experiment_id,
        "dwell_ms": dwell_ms,
    })
    if len(buffer) >= flush_at:
        flush(engine, state=store)


def flush(engine: Engine, state: MutableMapping | None = None) -> int:
    store = _state(state)
    buffer: list[dict[str, Any]] = store.get(BUFFER_KEY) or []
    if not buffer:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(db.event), buffer)
    written = len(buffer)
    store[BUFFER_KEY] = []
    return written


def now_ms() -> int:
    return int(time.monotonic() * 1000)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_analytics.py -v`
Expected: 12 passed.

- [ ] **Step 5: Set IDENTITY_LABEL from the spike, then commit**

Edit `IDENTITY_LABEL` in `hub/analytics.py` to match `docs/deployment-notes.md`.

```bash
git add hub/analytics.py tests/test_analytics.py
git commit -m "feat: add anonymous analytics capture with salted IP hashing"
```

---

### Task 10: Theme and page chrome

**Files:**
- Create: `hub/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hub.theme.PALETTE: dict[str, str]` — keys `ink`, `ink_soft`, `accent`, `accent_soft`, `cyan`, `surface`, `border`, `text`, `text_dim`.
  - `hub.theme.dark_page_css() -> str` — the `<style>` block for hub-chrome pages.
  - `hub.theme.experiment_header_css() -> str` — the slim bar shown above vendored content.
  - `hub.theme.inject(css: str) -> None` — writes it via `st.markdown`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme.py`:

```python
from hub import theme


def test_palette_has_required_tokens() -> None:
    required = {"ink", "ink_soft", "accent", "accent_soft", "cyan",
                "surface", "border", "text", "text_dim"}
    assert required <= set(theme.PALETTE)


def test_dark_css_is_wrapped_in_a_style_tag() -> None:
    css = theme.dark_page_css()
    assert css.strip().startswith("<style>")
    assert css.strip().endswith("</style>")


def test_dark_css_scopes_itself_to_hub_chrome() -> None:
    """The dark treatment must never leak into a vendored experiment body."""
    css = theme.dark_page_css()
    assert ".hub-dark" in css


def test_experiment_header_css_does_not_restyle_the_page_background() -> None:
    css = theme.experiment_header_css()
    assert ".stApp" not in css
    assert ".hub-expbar" in css
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: FAIL with `ImportError: cannot import name 'theme' from 'hub'`

- [ ] **Step 3: Implement**

Create `hub/theme.py`:

```python
"""Visual identity for the hub chrome.

The global Streamlit theme is light, because every vendored dashboard hardcodes
light-coloured boxes (`background-color: white`, `#f0f8ff`, `#f8f9fa`) with
default text colour — a dark global theme would put light text on them and make
them unreadable.

So the dark, animated treatment is scoped to `.hub-dark`, which only wraps hub
chrome: home, topic pages, locked teasers and admin. Experiment pages get a slim
dark header bar and nothing else.

Palette: Adelaide-inspired (red accent over deep navy), not official branding.
"""
from __future__ import annotations

import streamlit as st

PALETTE = {
    "ink": "#0B1020",
    "ink_soft": "#141A2E",
    "accent": "#C8102E",
    "accent_soft": "#F0435F",
    "cyan": "#31E1F7",
    "surface": "rgba(255,255,255,0.055)",
    "border": "rgba(255,255,255,0.13)",
    "text": "#F2F4F8",
    "text_dim": "rgba(242,244,248,0.66)",
}


def inject(css: str) -> None:
    st.markdown(css, unsafe_allow_html=True)


def dark_page_css() -> str:
    p = PALETTE
    return f"""<style>
.hub-dark {{
  background:
    radial-gradient(1100px 520px at 12% -10%, rgba(200,16,46,0.30), transparent 60%),
    radial-gradient(900px 460px at 88% 8%, rgba(49,225,247,0.16), transparent 62%),
    linear-gradient(168deg, {p['ink']} 0%, {p['ink_soft']} 100%);
  color: {p['text']};
  border-radius: 22px;
  padding: 2.6rem 2.2rem 2.2rem;
  margin-bottom: 1.4rem;
  position: relative;
  overflow: hidden;
}}
.hub-dark::after {{
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(circle at 50% 0%, #000 0%, transparent 78%);
}}
.hub-dark h1, .hub-dark h2, .hub-dark h3, .hub-dark p, .hub-dark span {{
  color: {p['text']};
}}
.hub-eyebrow {{
  letter-spacing: .22em; text-transform: uppercase;
  font-size: .70rem; color: {p['cyan']}; font-weight: 700;
}}
.hub-title {{
  font-size: clamp(1.9rem, 4.2vw, 3.0rem); font-weight: 800;
  line-height: 1.06; margin: .35rem 0 .5rem;
  background: linear-gradient(96deg, {p['text']} 12%, {p['accent_soft']} 58%, {p['cyan']} 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.hub-sub {{ color: {p['text_dim']}; font-size: 1.02rem; max-width: 62ch; }}
.hub-progress {{
  height: 7px; border-radius: 99px; background: rgba(255,255,255,0.11);
  overflow: hidden; margin: 1.3rem 0 .45rem; max-width: 460px;
}}
.hub-progress > span {{
  display: block; height: 100%;
  background: linear-gradient(90deg, {p['accent']}, {p['cyan']});
}}
/* Cards sit in st.columns, which we cannot wrap in .hub-dark, so each card
   carries its own dark surface rather than relying on a parent. */
.hub-card {{
  background:
    linear-gradient(158deg, rgba(11,16,32,0.97) 0%, rgba(20,26,46,0.97) 100%);
  border: 1px solid {p['border']};
  color: {p['text']};
  border-radius: 16px; padding: 1.15rem 1.15rem 1rem;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
  height: 100%;
}}
.hub-card h3, .hub-card span {{ color: {p['text']}; }}
.hub-card:hover {{
  transform: translateY(-4px);
  border-color: rgba(240,67,95,0.55);
  box-shadow: 0 14px 36px rgba(0,0,0,0.42);
}}
.hub-card.locked {{ opacity: .60; }}
.hub-card h3 {{ font-size: 1.10rem; margin: .3rem 0 .35rem; font-weight: 700; }}
.hub-card p {{ color: {p['text_dim']}; font-size: .89rem; margin: 0 0 .55rem; }}
.hub-chip {{
  display: inline-block; padding: .16rem .58rem; border-radius: 99px;
  font-size: .68rem; font-weight: 700; letter-spacing: .05em;
  border: 1px solid {p['border']}; color: {p['text_dim']};
}}
.hub-chip.open {{ color: {p['cyan']}; border-color: rgba(49,225,247,0.45); }}
@media (prefers-reduced-motion: reduce) {{
  .hub-card {{ transition: none; }}
  .hub-card:hover {{ transform: none; }}
}}
</style>"""


def experiment_header_css() -> str:
    p = PALETTE
    return f"""<style>
.hub-expbar {{
  background: linear-gradient(96deg, {p['ink']}, {p['ink_soft']});
  color: {p['text']};
  border-radius: 13px;
  padding: .78rem 1.05rem;
  margin-bottom: 1.05rem;
  display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
}}
.hub-expbar .crumb {{ color: {p['text_dim']}; font-size: .80rem; }}
.hub-expbar .now {{ color: {p['text']}; font-weight: 700; font-size: 1.02rem; }}
.hub-expbar .dot {{ color: {p['accent_soft']}; }}
</style>"""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/theme.py tests/test_theme.py
git commit -m "feat: add scoped dark hub chrome that never leaks into experiments"
```

---

### Task 11: Routing and navigation

**Files:**
- Create: `hub/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `hub.db`.
- Produces:
  - `hub.router.Route` — frozen dataclass with `view: str`, `topic_id: int | None`, `experiment_id: str | None`.
  - `hub.router.parse_route(params: Mapping[str, str]) -> Route` — `view` is one of `home`, `topic`, `experiment`, `admin`; unknown views fall back to `home`; non-integer topic ids fall back to `home`.
  - `hub.router.route_params(route: Route) -> dict[str, str]` — inverse, for building links.
  - `hub.router.render_sidebar_nav(engine, route: Route) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_router.py`:

```python
from hub.router import Route, parse_route, route_params


def test_empty_params_give_home() -> None:
    assert parse_route({}) == Route(view="home", topic_id=None, experiment_id=None)


def test_topic_route_parses_integer_id() -> None:
    assert parse_route({"view": "topic", "topic": "4"}) == Route("topic", 4, None)


def test_experiment_route_keeps_id_string() -> None:
    route = parse_route({"view": "experiment", "exp": "w7.pareto"})
    assert route == Route("experiment", None, "w7.pareto")


def test_admin_route() -> None:
    assert parse_route({"admin": "1"}).view == "admin"


def test_unknown_view_falls_back_home() -> None:
    assert parse_route({"view": "teleport"}).view == "home"


def test_non_integer_topic_falls_back_home() -> None:
    assert parse_route({"view": "topic", "topic": "abc"}).view == "home"


def test_topic_view_without_id_falls_back_home() -> None:
    assert parse_route({"view": "topic"}).view == "home"


def test_experiment_view_without_id_falls_back_home() -> None:
    assert parse_route({"view": "experiment"}).view == "home"


def test_route_params_round_trip() -> None:
    for route in (
        Route("home", None, None),
        Route("topic", 7, None),
        Route("experiment", None, "w2.consumer_model"),
    ):
        assert parse_route(route_params(route)) == route
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.router'`

- [ ] **Step 3: Implement**

Create `hub/router.py`:

```python
"""Query-parameter routing.

A single Streamlit page with `?view=` routing rather than st.navigation, because
topics are database rows that the instructor creates and renames at runtime —
there is no fixed page list to declare. It also makes every experiment a
shareable URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import streamlit as st

from hub import db

VIEWS = {"home", "topic", "experiment", "admin"}


@dataclass(frozen=True)
class Route:
    view: str
    topic_id: int | None
    experiment_id: str | None


def parse_route(params: Mapping[str, str]) -> Route:
    home = Route("home", None, None)

    if params.get("admin") == "1":
        return Route("admin", None, None)

    view = params.get("view", "home")
    if view not in VIEWS:
        return home

    if view == "topic":
        raw = params.get("topic")
        if raw is None:
            return home
        try:
            return Route("topic", int(raw), None)
        except (TypeError, ValueError):
            return home

    if view == "experiment":
        exp = params.get("exp")
        return Route("experiment", None, exp) if exp else home

    return home


def route_params(route: Route) -> dict[str, str]:
    if route.view == "admin":
        return {"admin": "1"}
    if route.view == "topic" and route.topic_id is not None:
        return {"view": "topic", "topic": str(route.topic_id)}
    if route.view == "experiment" and route.experiment_id:
        return {"view": "experiment", "exp": route.experiment_id}
    return {"view": "home"}


def go(route: Route) -> None:
    """Navigate, preserving the anonymous device id if one is in use."""
    device = st.query_params.get("d")
    params = route_params(route)
    if device:
        params["d"] = device
    st.query_params.clear()
    st.query_params.update(params)
    st.rerun()


def render_sidebar_nav(engine, route: Route) -> None:
    """Hub navigation above whatever the vendored module puts in the sidebar."""
    with st.sidebar:
        st.markdown("### ⚡ Course Modules")
        if st.button("Home", use_container_width=True, key="_hub.nav_home"):
            go(Route("home", None, None))

        for topic in db.list_topics(engine, include_disabled=False):
            experiments = db.list_experiments(
                engine, topic_id=topic["id"], include_disabled=False
            )
            if not experiments:
                continue
            with st.expander(topic["name"], expanded=route.topic_id == topic["id"]):
                for exp in experiments:
                    active = exp["experiment_id"] == route.experiment_id
                    label = ("▸ " if active else "") + exp["title"]
                    if st.button(
                        label, use_container_width=True,
                        key=f"_hub.nav_{exp['experiment_id']}",
                    ):
                        go(Route("experiment", None, exp["experiment_id"]))
        st.divider()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_router.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/router.py tests/test_router.py
git commit -m "feat: add query-parameter routing and sidebar navigation"
```

---

### Task 12: Student pages — home, topic, locked

**Files:**
- Create: `hub/pages_student.py`
- Test: `tests/test_pages_student.py`

**Interfaces:**
- Consumes: `hub.db`, `hub.theme`, `hub.router`.
- Produces:
  - `hub.pages_student.topic_status(topic: dict, experiments: list[dict]) -> tuple[bool, str]` — `(is_open, chip_label)`. A topic is open when it is enabled and has at least one enabled, non-orphaned experiment.
  - `hub.pages_student.render_home(engine) -> None`
  - `hub.pages_student.render_topic(engine, topic_id: int) -> None`
  - `hub.pages_student.render_locked(engine, topic: dict) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pages_student.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pages_student.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.pages_student'`

- [ ] **Step 3: Implement**

Create `hub/pages_student.py`:

```python
"""Student-facing pages: the home card grid, a topic's experiment list, and the
teaser shown for content that is not open yet.

Locked content is gated by *not rendering it*: a disabled experiment's code
never executes. What a student can see is its title and unlock message, which is
the point — they should know what is coming.
"""
from __future__ import annotations

import html

import streamlit as st

from hub import db, theme
from hub.router import Route, go


def topic_status(topic: dict, experiments: list[dict]) -> tuple[bool, str]:
    """Is this topic open, and what should its chip say?"""
    available = [
        e for e in experiments if e.get("enabled") and not e.get("orphaned")
    ]
    if not topic.get("enabled") or not available:
        return False, "🔒 Not yet available"
    count = len(available)
    return True, f"{count} experiment{'s' if count != 1 else ''}"


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def render_home(engine) -> None:
    theme.inject(theme.dark_page_css())
    topics = db.list_topics(engine, include_disabled=True)

    cards = []
    open_count = 0
    for topic in topics:
        experiments = db.list_experiments(
            engine, topic_id=topic["id"], include_disabled=True
        )
        is_open, chip = topic_status(topic, experiments)
        open_count += int(is_open)
        cards.append((topic, is_open, chip))

    total = len(cards) or 1
    pct = int(100 * open_count / total)

    st.markdown(
        f"""<div class="hub-dark">
  <div class="hub-eyebrow">ELEC ENG 4087/7087 · University of Adelaide</div>
  <div class="hub-title">Electricity Market &amp;<br/>Power Systems Operation</div>
  <div class="hub-sub">Interactive experiments for the concepts we build up across
  the course — supply and demand, market power, optimisation, duality, dispatch
  and power flow. Open one and change the numbers.</div>
  <div class="hub-progress"><span style="width:{pct}%"></span></div>
  <div class="hub-sub" style="font-size:.85rem">{open_count} of {len(cards)} topics available</div>
</div>""",
        unsafe_allow_html=True,
    )

    columns = st.columns(3, gap="medium")
    for index, (topic, is_open, chip) in enumerate(cards):
        with columns[index % 3]:
            st.markdown(
                f"""<div class="hub-card {'' if is_open else 'locked'}">
  <span class="hub-chip {'open' if is_open else ''}">{_esc(chip)}</span>
  <h3>{_esc(topic['name'])}</h3>
  <p>{_esc(topic['subtitle'])}</p>
</div>""",
                unsafe_allow_html=True,
            )
            label = "Open" if is_open else "Preview"
            if st.button(label, key=f"_hub.card_{topic['id']}", use_container_width=True):
                go(Route("topic", topic["id"], None))

    st.caption(
        "This site records anonymous usage statistics (which experiments are opened "
        "and for how long) to help improve the course material. No account, name or "
        "email is collected, and no IP address is stored — only a one-way hash that "
        "cannot be traced back to you."
    )


def render_topic(engine, topic_id: int) -> None:
    topics = {t["id"]: t for t in db.list_topics(engine, include_disabled=True)}
    topic = topics.get(topic_id)
    if topic is None:
        st.warning("That topic no longer exists.")
        if st.button("Back to home", key="_hub.topic_missing_home"):
            go(Route("home", None, None))
        return

    experiments = db.list_experiments(engine, topic_id=topic_id, include_disabled=True)
    is_open, _ = topic_status(topic, experiments)

    theme.inject(theme.dark_page_css())
    st.markdown(
        f"""<div class="hub-dark">
  <div class="hub-eyebrow">Topic</div>
  <div class="hub-title" style="font-size:clamp(1.6rem,3.2vw,2.3rem)">{_esc(topic['name'])}</div>
  <div class="hub-sub">{_esc(topic['subtitle'])}</div>
</div>""",
        unsafe_allow_html=True,
    )

    if not is_open:
        render_locked(engine, topic)
        return

    available = [e for e in experiments if e["enabled"] and not e["orphaned"]]
    columns = st.columns(2, gap="medium")
    for index, exp in enumerate(available):
        with columns[index % 2]:
            st.markdown(
                f"""<div class="hub-card">
  <h3>{_esc(exp['title'])}</h3>
  <p>{_esc(exp['blurb'])}</p>
</div>""",
                unsafe_allow_html=True,
            )
            if st.button(
                "Open experiment", key=f"_hub.exp_{exp['experiment_id']}",
                use_container_width=True,
            ):
                go(Route("experiment", None, exp["experiment_id"]))

    st.divider()
    if st.button("← All topics", key="_hub.topic_back"):
        go(Route("home", None, None))


def render_locked(engine, topic: dict) -> None:
    """Teaser for a topic that is not open yet."""
    experiments = db.list_experiments(
        engine, topic_id=topic["id"], include_disabled=True
    )
    listed = "".join(
        f"<li>{_esc(e['title'])}"
        + (f" — {_esc(e['blurb'])}" if e["blurb"] else "")
        + "</li>"
        for e in experiments if not e["orphaned"]
    )
    message = topic["unlock_message"] or "This content is not available yet."

    theme.inject(theme.dark_page_css())
    st.markdown(
        f"""<div class="hub-dark">
  <span class="hub-chip">🔒 Locked</span>
  <div class="hub-title" style="font-size:clamp(1.4rem,3vw,2rem)">{_esc(message)}</div>
  <div class="hub-sub">When this opens you will be able to work through:</div>
  <ul class="hub-sub">{listed}</ul>
</div>""",
        unsafe_allow_html=True,
    )
    if st.button("← All topics", key="_hub.locked_back"):
        go(Route("home", None, None))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pages_student.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/pages_student.py tests/test_pages_student.py
git commit -m "feat: add home grid, topic list and locked teaser pages"
```

---

### Task 13: Experiment page, app entry point, dwell tracking

Replaces the Task 2 spike content of `app.py`.

**Files:**
- Modify: `app.py` (full rewrite)
- Create: `hub/pages_experiment.py`
- Test: `tests/test_pages_experiment.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `hub.pages_experiment.resolve_access(row: dict | None, catalogue: dict) -> tuple[str, str]` — returns `(status, message)` where status is one of `ok`, `missing`, `disabled`, `orphaned`.
  - `hub.pages_experiment.render_experiment_page(engine, experiment_id: str, catalogue: dict) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pages_experiment.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pages_experiment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.pages_experiment'`

- [ ] **Step 3: Implement the experiment page**

Create `hub/pages_experiment.py`:

```python
"""Renders one experiment: hub chrome, then the vendored dashboard verbatim.

Access is checked here, before the runner is called, so a disabled experiment's
code is never executed even if someone types its URL directly.
"""
from __future__ import annotations

import html

import streamlit as st

from hub import analytics, db, theme
from hub.catalogue import Experiment
from hub.router import Route, go
from hub.runner import ExperimentRenderError, render_experiment

OPEN_TS_KEY = "_hub.open_ts"
OPEN_EXP_KEY = "_hub.open_exp"


def resolve_access(row: dict | None, catalogue: dict[str, Experiment]) -> tuple[str, str]:
    """Decide whether this experiment may render."""
    if row is None:
        return "missing", "That experiment does not exist."
    if row.get("orphaned") or row["experiment_id"] not in catalogue:
        return "orphaned", "That experiment is no longer part of the course site."
    if not row.get("enabled"):
        return "disabled", "This experiment is not available yet."
    return "ok", ""


def close_previous(engine, current_experiment_id: str | None) -> None:
    """Emit a dwell event when the student leaves an experiment."""
    previous = st.session_state.get(OPEN_EXP_KEY)
    if previous and previous != current_experiment_id:
        opened_at = st.session_state.get(OPEN_TS_KEY)
        dwell = analytics.now_ms() - opened_at if opened_at else None
        analytics.track(
            engine, "experiment_close", experiment_id=previous, dwell_ms=dwell
        )
        analytics.flush(engine)
        st.session_state.pop(OPEN_EXP_KEY, None)
        st.session_state.pop(OPEN_TS_KEY, None)


def render_experiment_page(engine, experiment_id: str, catalogue: dict) -> None:
    row = db.get_experiment(engine, experiment_id)
    status, message = resolve_access(row, catalogue)

    if status != "ok":
        theme.inject(theme.dark_page_css())
        st.markdown(
            f"""<div class="hub-dark">
  <span class="hub-chip">🔒 Unavailable</span>
  <div class="hub-title" style="font-size:clamp(1.4rem,3vw,2rem)">{html.escape(message)}</div>
</div>""",
            unsafe_allow_html=True,
        )
        if st.button("← All topics", key="_hub.exp_denied_back"):
            go(Route("home", None, None))
        return

    topics = {t["id"]: t for t in db.list_topics(engine, include_disabled=True)}
    topic = topics.get(row["topic_id"]) or {"name": "Unassigned", "id": None}

    if st.session_state.get(OPEN_EXP_KEY) != experiment_id:
        st.session_state[OPEN_EXP_KEY] = experiment_id
        st.session_state[OPEN_TS_KEY] = analytics.now_ms()
        analytics.track(
            engine, "experiment_open",
            topic_id=topic.get("id"), experiment_id=experiment_id,
        )

    theme.inject(theme.experiment_header_css())
    st.markdown(
        f"""<div class="hub-expbar">
  <span class="crumb">{html.escape(topic['name'])}</span>
  <span class="dot">·</span>
  <span class="now">{html.escape(row['title'])}</span>
</div>""",
        unsafe_allow_html=True,
    )

    try:
        render_experiment(catalogue[experiment_id])
    except ExperimentRenderError as exc:
        st.error(
            "This experiment could not be loaded. The course coordinator has been "
            "shown the technical detail below."
        )
        st.exception(exc)
```

- [ ] **Step 4: Rewrite `app.py` as the real entry point**

Replace the entire contents of `app.py`:

```python
"""Electricity Market Course — unified dashboard hub.

Entry point: sets up the page, reconciles the catalogue against the database,
and dispatches on the query-string route.
"""
from __future__ import annotations

import streamlit as st

from hub import analytics, admin, db, pages_experiment, pages_student
from hub.catalogue import load_catalogue
from hub.router import parse_route, render_sidebar_nav

st.set_page_config(
    page_title="Electricity Market & Power Systems Operation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _startup():
    """Bootstrap, seed and reconcile exactly once per app boot."""
    catalogue = load_catalogue()
    engine = db.get_engine()
    db.bootstrap(engine)
    db.seed_initial(engine, catalogue)
    db.reconcile(engine, catalogue)
    return engine, catalogue


def main() -> None:
    engine, catalogue = _startup()
    route = parse_route(st.query_params)

    if route.view == "admin":
        admin.render(engine, catalogue)
        return

    analytics.ensure_session(engine)
    pages_experiment.close_previous(
        engine, route.experiment_id if route.view == "experiment" else None
    )
    render_sidebar_nav(engine, route)

    if route.view == "topic" and route.topic_id is not None:
        analytics.track(engine, "topic_view", topic_id=route.topic_id)
        pages_student.render_topic(engine, route.topic_id)
    elif route.view == "experiment" and route.experiment_id:
        pages_experiment.render_experiment_page(engine, route.experiment_id, catalogue)
    else:
        analytics.track(engine, "home_view")
        pages_student.render_home(engine)

    analytics.flush(engine)


main()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pages_experiment.py -v`
Expected: 7 passed. (`app.py` itself will not import until Task 15 creates `hub/admin.py` — that is expected, and is why this test targets `hub.pages_experiment` directly rather than running the app.)

- [ ] **Step 6: Commit**

```bash
git add app.py hub/pages_experiment.py tests/test_pages_experiment.py
git commit -m "feat: add experiment page with access control and dwell tracking"
```

---

### Task 14: Admin authentication

**Files:**
- Create: `hub/admin_auth.py`
- Test: `tests/test_admin_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `hub.admin_auth.MAX_ATTEMPTS: int` = 5, `hub.admin_auth.LOCKOUT_SECONDS: int` = 900.
  - `hub.admin_auth.password_matches(supplied: str, expected: str) -> bool` — constant-time.
  - `hub.admin_auth.register_failure(state: MutableMapping, now: float) -> None`
  - `hub.admin_auth.lockout_remaining(state: MutableMapping, now: float) -> int` — seconds remaining, 0 if not locked out.
  - `hub.admin_auth.clear_failures(state: MutableMapping) -> None`
  - `hub.admin_auth.require_admin(state=None) -> bool` — renders the login form; returns True when authorised.

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_auth.py`:

```python
from hub import admin_auth


def test_correct_password_matches() -> None:
    assert admin_auth.password_matches("hunter2", "hunter2") is True


def test_wrong_password_does_not_match() -> None:
    assert admin_auth.password_matches("hunter3", "hunter2") is False


def test_empty_password_never_matches_empty_expected() -> None:
    """A blank configured password must not become a skeleton key."""
    assert admin_auth.password_matches("", "") is False


def test_no_lockout_before_threshold() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS - 1):
        admin_auth.register_failure(state, now=100.0 + i)
    assert admin_auth.lockout_remaining(state, now=200.0) == 0


def test_lockout_engages_at_threshold() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    remaining = admin_auth.lockout_remaining(state, now=104.0)
    assert remaining > 0


def test_lockout_expires_after_the_window() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    later = 104.0 + admin_auth.LOCKOUT_SECONDS + 1
    assert admin_auth.lockout_remaining(state, now=later) == 0


def test_clear_failures_resets_lockout() -> None:
    state: dict = {}
    for i in range(admin_auth.MAX_ATTEMPTS):
        admin_auth.register_failure(state, now=100.0 + i)
    admin_auth.clear_failures(state)
    assert admin_auth.lockout_remaining(state, now=105.0) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_admin_auth.py -v`
Expected: FAIL with `ImportError: cannot import name 'admin_auth' from 'hub'`

- [ ] **Step 3: Implement**

Create `hub/admin_auth.py`:

```python
"""Password gate for the admin panel.

Deliberately simple: one shared password from deployment secrets, compared in
constant time, with a lockout so it cannot be ground down by guessing. There is
no student login anywhere on this site — this gate exists only to keep the
usage data and content toggles to the course coordinator.
"""
from __future__ import annotations

import hmac
import time
from typing import MutableMapping

import streamlit as st

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
ATTEMPT_DELAY_SECONDS = 1.0

AUTHED_KEY = "_hub.admin_ok"
FAILURES_KEY = "_hub.admin_failures"
LOCKED_AT_KEY = "_hub.admin_locked_at"


def password_matches(supplied: str, expected: str) -> bool:
    if not supplied or not expected:
        return False
    return hmac.compare_digest(str(supplied), str(expected))


def register_failure(state: MutableMapping, now: float) -> None:
    failures = int(state.get(FAILURES_KEY, 0)) + 1
    state[FAILURES_KEY] = failures
    if failures >= MAX_ATTEMPTS:
        state[LOCKED_AT_KEY] = now


def lockout_remaining(state: MutableMapping, now: float) -> int:
    locked_at = state.get(LOCKED_AT_KEY)
    if locked_at is None:
        return 0
    elapsed = now - float(locked_at)
    if elapsed >= LOCKOUT_SECONDS:
        state.pop(LOCKED_AT_KEY, None)
        state[FAILURES_KEY] = 0
        return 0
    return int(LOCKOUT_SECONDS - elapsed)


def clear_failures(state: MutableMapping) -> None:
    state.pop(FAILURES_KEY, None)
    state.pop(LOCKED_AT_KEY, None)


def require_admin(state: MutableMapping | None = None) -> bool:
    """Render the gate. Returns True only when authorised."""
    store = st.session_state if state is None else state
    if store.get(AUTHED_KEY):
        return True

    st.title("Course coordinator sign-in")

    remaining = lockout_remaining(store, time.monotonic())
    if remaining:
        st.error(f"Too many attempts. Try again in {remaining // 60 + 1} minute(s).")
        return False

    supplied = st.text_input("Password", type="password", key="_hub.admin_pw")
    if not st.button("Sign in", key="_hub.admin_signin"):
        return False

    time.sleep(ATTEMPT_DELAY_SECONDS)
    if password_matches(supplied, st.secrets.get("admin", {}).get("password", "")):
        clear_failures(store)
        store[AUTHED_KEY] = True
        st.rerun()

    register_failure(store, time.monotonic())
    st.error("Incorrect password.")
    return False
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_admin_auth.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add hub/admin_auth.py tests/test_admin_auth.py
git commit -m "feat: add admin password gate with lockout"
```

---

### Task 15: Admin panel — usage, content, export

**Files:**
- Create: `hub/admin.py`
- Create: `hub/queries.py`
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: `hub.db`, `hub.admin_auth`, `hub.analytics.IDENTITY_LABEL`.
- Produces:
  - `hub.queries.usage_summary(engine, days: int) -> dict` — keys `unique_visitors: int`, `sessions: int`, `experiment_opens: int`.
  - `hub.queries.experiment_ranking(engine, days: int) -> list[dict]` — keys `experiment_id`, `title`, `opens`, `median_dwell_s`, ordered by `opens` descending.
  - `hub.queries.events_dataframe(engine) -> pandas.DataFrame` — every event, for CSV export.
  - `hub.admin.render(engine, catalogue) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_queries.py`:

```python
import datetime as dt

import pytest
from sqlalchemy import create_engine, insert

from hub import db, queries
from hub.catalogue import load_catalogue


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    db.bootstrap(eng)
    db.seed_initial(eng, load_catalogue())
    now = dt.datetime.now(dt.timezone.utc)
    with eng.begin() as conn:
        conn.execute(insert(db.visitor_session), [
            {"id": "s1", "ip_hash": "hashA", "first_seen": now},
            {"id": "s2", "ip_hash": "hashA", "first_seen": now},
            {"id": "s3", "ip_hash": "hashB", "first_seen": now},
        ])
        conn.execute(insert(db.event), [
            {"session_id": "s1", "kind": "experiment_open",
             "experiment_id": "w2.consumer_model", "ts": now},
            {"session_id": "s2", "kind": "experiment_open",
             "experiment_id": "w2.consumer_model", "ts": now},
            {"session_id": "s3", "kind": "experiment_open",
             "experiment_id": "w7.pareto", "ts": now},
            {"session_id": "s1", "kind": "experiment_close",
             "experiment_id": "w2.consumer_model", "dwell_ms": 10_000, "ts": now},
            {"session_id": "s2", "kind": "experiment_close",
             "experiment_id": "w2.consumer_model", "dwell_ms": 30_000, "ts": now},
            {"session_id": "s1", "kind": "home_view", "ts": now},
        ])
    return eng


def test_unique_visitors_counts_distinct_hashes_not_sessions(engine) -> None:
    summary = queries.usage_summary(engine, days=30)
    assert summary["unique_visitors"] == 2
    assert summary["sessions"] == 3


def test_experiment_opens_excludes_other_event_kinds(engine) -> None:
    assert queries.usage_summary(engine, days=30)["experiment_opens"] == 3


def test_ranking_orders_by_opens(engine) -> None:
    ranking = queries.experiment_ranking(engine, days=30)
    assert ranking[0]["experiment_id"] == "w2.consumer_model"
    assert ranking[0]["opens"] == 2


def test_ranking_uses_display_title_from_database(engine) -> None:
    ranking = queries.experiment_ranking(engine, days=30)
    assert ranking[0]["title"] == "Consumer Model"


def test_ranking_reports_median_dwell_in_seconds(engine) -> None:
    ranking = queries.experiment_ranking(engine, days=30)
    top = next(r for r in ranking if r["experiment_id"] == "w2.consumer_model")
    assert top["median_dwell_s"] == pytest.approx(20.0)


def test_ranking_handles_experiments_with_no_close_event(engine) -> None:
    ranking = queries.experiment_ranking(engine, days=30)
    pareto = next(r for r in ranking if r["experiment_id"] == "w7.pareto")
    assert pareto["opens"] == 1
    assert pareto["median_dwell_s"] is None


def test_events_dataframe_returns_every_event(engine) -> None:
    frame = queries.events_dataframe(engine)
    assert len(frame) == 6
    assert "kind" in frame.columns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_queries.py -v`
Expected: FAIL with `ImportError: cannot import name 'queries' from 'hub'`

- [ ] **Step 3: Implement the queries**

Create `hub/queries.py`:

```python
"""Read-side analytics queries for the admin panel.

Medians are computed in Python rather than SQL so the same code runs on both
SQLite (tests) and Postgres (production).
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from hub import db


def _cutoff(days: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


def usage_summary(engine: Engine, days: int) -> dict[str, int]:
    since = _cutoff(days)
    with engine.connect() as conn:
        unique_visitors = conn.execute(
            select(func.count(func.distinct(db.visitor_session.c.ip_hash)))
            .where(db.visitor_session.c.first_seen >= since)
        ).scalar_one()
        sessions = conn.execute(
            select(func.count()).select_from(db.visitor_session)
            .where(db.visitor_session.c.first_seen >= since)
        ).scalar_one()
        opens = conn.execute(
            select(func.count()).select_from(db.event)
            .where(db.event.c.kind == "experiment_open", db.event.c.ts >= since)
        ).scalar_one()
    return {
        "unique_visitors": int(unique_visitors or 0),
        "sessions": int(sessions or 0),
        "experiment_opens": int(opens or 0),
    }


def experiment_ranking(engine: Engine, days: int) -> list[dict[str, Any]]:
    since = _cutoff(days)
    with engine.connect() as conn:
        opens = dict(conn.execute(
            select(db.event.c.experiment_id, func.count())
            .where(db.event.c.kind == "experiment_open", db.event.c.ts >= since)
            .group_by(db.event.c.experiment_id)
        ).all())

        dwells: dict[str, list[int]] = {}
        for exp_id, dwell in conn.execute(
            select(db.event.c.experiment_id, db.event.c.dwell_ms)
            .where(db.event.c.kind == "experiment_close",
                   db.event.c.ts >= since,
                   db.event.c.dwell_ms.is_not(None))
        ).all():
            dwells.setdefault(exp_id, []).append(int(dwell))

        titles = dict(conn.execute(
            select(db.experiment.c.experiment_id, db.experiment.c.title)
        ).all())

    rows = [
        {
            "experiment_id": exp_id,
            "title": titles.get(exp_id, exp_id),
            "opens": int(count),
            "median_dwell_s": (
                round(statistics.median(dwells[exp_id]) / 1000, 1)
                if dwells.get(exp_id) else None
            ),
        }
        for exp_id, count in opens.items()
    ]
    return sorted(rows, key=lambda r: r["opens"], reverse=True)


def events_dataframe(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.DataFrame(
            [dict(r._mapping) for r in conn.execute(select(db.event))]
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_queries.py -v`
Expected: 7 passed.

- [ ] **Step 5: Implement the admin UI**

Create `hub/admin.py`:

```python
"""Admin panel: usage, content arrangement, export.

The content tab is the one that matters day to day — it is how experiments get
assigned to topics and switched on as the course progresses, without a redeploy.
"""
from __future__ import annotations

import streamlit as st

from hub import admin_auth, analytics, db, queries, theme
from hub.router import Route, go


def render(engine, catalogue) -> None:
    if not admin_auth.require_admin():
        return

    theme.inject(theme.dark_page_css())
    st.markdown(
        """<div class="hub-dark">
  <div class="hub-eyebrow">Course coordinator</div>
  <div class="hub-title" style="font-size:clamp(1.5rem,3vw,2.2rem)">Dashboard admin</div>
</div>""",
        unsafe_allow_html=True,
    )

    if st.button("← Back to the student site", key="_hub.admin_exit"):
        go(Route("home", None, None))

    usage_tab, content_tab, export_tab = st.tabs(["Usage", "Content", "Export"])

    with usage_tab:
        _render_usage(engine)
    with content_tab:
        _render_content(engine, catalogue)
    with export_tab:
        _render_export(engine)


def _render_usage(engine) -> None:
    days = st.selectbox(
        "Period", [7, 30, 90, 365],
        format_func=lambda d: f"Last {d} days", index=1, key="_hub.admin_days",
    )
    summary = queries.usage_summary(engine, days)

    left, middle, right = st.columns(3)
    left.metric(analytics.IDENTITY_LABEL, summary["unique_visitors"])
    middle.metric("Sessions", summary["sessions"])
    right.metric("Experiment opens", summary["experiment_opens"])

    st.caption(
        f'"{analytics.IDENTITY_LABEL}" reflects what this deployment can actually '
        "measure — see docs/deployment-notes.md."
    )

    st.subheader("Which experiments students actually use")
    ranking = queries.experiment_ranking(engine, days)
    if not ranking:
        st.info("No experiment opens recorded in this period yet.")
        return
    st.dataframe(
        ranking, use_container_width=True, hide_index=True,
        column_config={
            "experiment_id": "ID",
            "title": "Experiment",
            "opens": st.column_config.NumberColumn("Opens"),
            "median_dwell_s": st.column_config.NumberColumn(
                "Median time (s)", help="Median seconds spent before navigating away"
            ),
        },
    )


def _render_content(engine, catalogue) -> None:
    st.subheader("Topics")
    topics = db.list_topics(engine, include_disabled=True)
    topic_choices = {None: "— unassigned —"} | {t["id"]: t["name"] for t in topics}

    for topic in topics:
        with st.expander(f"{topic['name']} — {topic['subtitle']}", expanded=False):
            name = st.text_input("Name", topic["name"], key=f"_hub.tn_{topic['id']}")
            subtitle = st.text_input(
                "Subtitle", topic["subtitle"], key=f"_hub.ts_{topic['id']}"
            )
            unlock = st.text_input(
                "Unlock message (shown while locked)", topic["unlock_message"],
                key=f"_hub.tu_{topic['id']}",
            )
            order = st.number_input(
                "Order", value=int(topic["sort_order"]), step=1,
                key=f"_hub.to_{topic['id']}",
            )
            enabled = st.toggle(
                "Topic visible and open", value=bool(topic["enabled"]),
                key=f"_hub.te_{topic['id']}",
            )
            save, delete = st.columns(2)
            if save.button("Save topic", key=f"_hub.tsave_{topic['id']}"):
                db.upsert_topic(
                    engine, topic["id"], name, subtitle, unlock, int(order), enabled
                )
                st.rerun()
            if delete.button("Delete topic", key=f"_hub.tdel_{topic['id']}"):
                db.delete_topic(engine, topic["id"])
                st.rerun()

    with st.expander("Add a new topic"):
        new_name = st.text_input("Name", key="_hub.newtopic_name")
        new_sub = st.text_input("Subtitle", key="_hub.newtopic_sub")
        new_unlock = st.text_input(
            "Unlock message", "Available after the lecture for this week.",
            key="_hub.newtopic_unlock",
        )
        if st.button("Create topic", key="_hub.newtopic_create") and new_name:
            db.upsert_topic(
                engine, None, new_name, new_sub, new_unlock, len(topics), True
            )
            st.rerun()

    st.divider()
    st.subheader("Experiments")
    st.caption(
        "Every experiment can be moved to any topic and switched on or off "
        "independently, whichever dashboard it came from."
    )

    for row in db.list_experiments(engine, topic_id=None, include_disabled=True):
        exp_id = row["experiment_id"]
        flag = " ⚠️ orphaned" if row["orphaned"] else ""
        with st.expander(f"{row['title']} · {exp_id}{flag}", expanded=False):
            if row["orphaned"]:
                st.warning(
                    "This experiment is no longer in catalogue.yaml. It is hidden "
                    "from students but kept so its settings are not lost."
                )
            title = st.text_input("Title", row["title"], key=f"_hub.et_{exp_id}")
            blurb = st.text_area(
                "Blurb", row["blurb"], height=70, key=f"_hub.eb_{exp_id}"
            )
            keys = list(topic_choices)
            current = row["topic_id"] if row["topic_id"] in topic_choices else None
            topic_id = st.selectbox(
                "Topic", keys, index=keys.index(current),
                format_func=lambda k: topic_choices[k], key=f"_hub.ep_{exp_id}",
            )
            order = st.number_input(
                "Order within topic", value=int(row["sort_order"]), step=1,
                key=f"_hub.eo_{exp_id}",
            )
            enabled = st.toggle(
                "Available to students", value=bool(row["enabled"]),
                key=f"_hub.ee_{exp_id}",
            )
            if st.button("Save experiment", key=f"_hub.esave_{exp_id}"):
                db.update_experiment_text(engine, exp_id, title, blurb)
                db.assign_experiment(engine, exp_id, topic_id, int(order))
                db.set_experiment_enabled(engine, exp_id, enabled)
                st.rerun()


def _render_export(engine) -> None:
    frame = queries.events_dataframe(engine)
    st.write(f"{len(frame)} events recorded.")
    st.download_button(
        "Download events CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="electricity_market_hub_events.csv",
        mime="text/csv",
        key="_hub.export_csv",
    )
```

- [ ] **Step 6: Verify the whole app imports and the suite passes**

```bash
.venv/bin/python -c "import ast,sys; ast.parse(open('app.py').read())"
.venv/bin/python -m pytest -v -x --ignore=tests/test_experiments_render.py
```

Expected: all non-smoke tests pass.

- [ ] **Step 7: Commit**

```bash
git add hub/admin.py hub/queries.py tests/test_queries.py
git commit -m "feat: add admin panel with usage ranking, content control and export"
```

---

### Task 16: End-to-end verification and deployment

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment-notes.md`

**Interfaces:**
- Consumes: everything.
- Produces: a working public URL.

- [ ] **Step 1: Run the complete test suite**

```bash
cd "/Users/a1226603/Documents/Electricity Market Course"
.venv/bin/python -m pytest -v
```

Expected: every test passes, including all 51 smoke assertions. Do not proceed past a failure. If a vendored dashboard fails to render, fix `hub/runner.py` or `hub/tabsurgery.py` — **never** `sources/`.

- [ ] **Step 2: Run the app locally against the real Neon database**

Run: `.venv/bin/streamlit run app.py`

Verify by hand:
1. Home shows six topic cards, all open, dark styling.
2. Opening a topic lists its experiments; opening one renders the dashboard on a light background with its own sidebar controls intact.
3. Switching from a Week 7 experiment to a Week 8 experiment does not raise (this is the session-state isolation check).
4. `?admin=1` prompts for a password; a wrong one is rejected; the right one opens the panel.
5. In admin, disable one experiment; confirm it disappears from the student view and its direct URL now shows the unavailable page.
6. In admin, move one Week 2 experiment to the Week 8 topic; confirm it appears there.
7. Disable a whole topic; confirm the card shows the locked teaser with the unlock message.

- [ ] **Step 3: Write the README**

Replace `README.md`:

````markdown
# Electricity Market Course — Dashboard Hub

Unified Streamlit site collating the interactive experiments for
**ELEC ENG 4087/7087 — Electricity Market and Power Systems Operation**.

Live site: <deployed URL>

## How it fits together

- `sources/` — the six original dashboards, vendored **verbatim**. Never edit these.
  Use `python scripts/sync_sources.py` to re-pull them from their upstream repos.
- `catalogue.yaml` — how to render each of the 25 experiments. Edit only when adding
  or removing a dashboard.
- Database (Neon Postgres) — how each experiment is *presented*: topic, title, blurb,
  order, enabled. Edited live in the admin panel, no redeploy.
- `hub/` — the hub: routing, pages, isolation runner, analytics, admin.

## Admin

Append `?admin=1` to the site URL. The password is in the deployment secrets.

- **Usage** — visitors, sessions, and which experiments students actually open.
- **Content** — create topics, assign any experiment to any topic, toggle each on or off.
- **Export** — CSV of raw events.

## Adding a new dashboard

1. Drop the `.py` into `sources/`.
2. Add its entries to `catalogue.yaml` (`pin_selectbox` or `pin_tab`).
3. `pytest tests/test_experiments_render.py`
4. Push. New experiments arrive unassigned and disabled — place them in the admin panel.

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill it in
.venv/bin/streamlit run app.py
.venv/bin/python -m pytest
```
````

- [ ] **Step 4: Deploy and verify in production**

```bash
git add README.md
git commit -m "docs: document hub structure, admin and adding dashboards"
git push
```

Then, in the browser:
1. Confirm the Streamlit Cloud app rebuilt without errors (watch the deploy log for `pypsa` installing).
2. Confirm all three secrets are set in **Settings → Secrets**.
3. Open the public URL and repeat the seven manual checks from Step 2.
4. Open `?admin=1` and confirm the **Usage** tab now shows non-zero numbers, and that the visitor metric label matches what the deployment actually measures.

- [ ] **Step 5: Update the deployment notes and commit**

Append to `docs/deployment-notes.md` the live URL, the deploy date, observed cold-start time, and confirmation that the visitor metric label is correct.

```bash
git add docs/deployment-notes.md
git commit -m "docs: record production deployment verification"
git push
```

---

## Verification checklist

Against the spec's success criteria:

1. One public URL, no login — Task 16 Step 4.
2. All 25 experiments render identically — Task 7 (automated), Task 16 Step 2 (visual).
3. Assign, reorder, toggle live with no redeploy — Task 15, verified in Task 16 Step 2 items 5–7.
4. Unique visitors, sessions, opens, dwell — Task 15 usage tab.
5. Free hosting and data store — Streamlit Community Cloud and Neon free tiers.
6. Adding a dashboard is a file plus a YAML edit — README, Task 16 Step 3.
