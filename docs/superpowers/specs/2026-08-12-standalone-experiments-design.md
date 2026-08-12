# Standalone experiments: the hub becomes the source of truth

**Date:** 2026-08-12
**Status:** approved design, not yet implemented

## Problem

The six weekly dashboards under `sources/` are vendored byte-for-byte from six
upstream GitHub repos. `tests/test_sources_intact.py` re-downloads each one and
fails if the local copy differs, so every content change means editing the
upstream repo, running `scripts/sync_sources.py`, and committing the pulled
file — two repos per edit, six repos to maintain.

The bundling has a second cost. Each file holds 2–6 experiments behind a
sidebar dropdown or a tab strip, so `hub/runner.py` isolates one experiment by
monkeypatching the process-global `streamlit` module (`st.sidebar.selectbox`,
`st.tabs`, `st.set_page_config`) and rewriting the AST (`hub/tabsurgery.py`).
Because those patches are process-global, rendering is serialised behind
`_RENDER_LOCK`: two students in the same tutorial wait for each other.

Editing one experiment also means opening a 2000–2700 line file that contains
four other experiments.

## Goals

1. One repo. Experiments are edited here, directly.
2. Changing one experiment cannot break another.
3. Nothing in the filesystem is organised by week or topic — topic membership
   changes over time and already lives in the database.

## Non-goals

- No behaviour or visual changes. The split is faithful extraction; every
  experiment renders what it renders today.
- No tidying, reformatting, or dependency changes to the extracted code beyond
  what the extraction mechanically requires.
- The fate of the six upstream repos (archive or leave) is the coordinator's
  call and is outside this work.

## Measured basis for the layout

Call-graph analysis over the four multi-experiment files (entry point =
the `*_section` / `render_*` function the catalogue selects, walked
transitively over top-level functions):

| File | Experiments | Helpers reached by 2+ experiments | Helpers used by exactly one |
|---|---|---|---|
| week2_consumer_supplier.py | 5 | 1 (`calculate_elasticity`, 12 lines) | 11 |
| week3_pricing_market_power.py | 4 | 0 | 12 |
| week7_ed_viu.py | 5 | 2 (`get_problem_name`, `get_problem_description`; 10–11 lines) | 1 |
| week8_pf_auction.py | 5 | 0 | 4 |

Weeks 4 and 6 are absent from the table because they have no per-experiment
entry function at all: their content sits inline under `if page_option == ...`
(week 4) and inside `with tab1:` blocks (week 6). Their extraction is a lift of
the inline block into a `render()`, not a move of an existing function.

Almost nothing is shared through direct calls. The real shared surface is the
*preamble* weeks 7 and 8 run before their tabs — session-state init, the input
sidebar, and the solve step that every tab in the file consumes:

- week 7: `initialize_session_state` (20), `render_sidebar` (68),
  `solve_all_problems` (22), `create_demand_profile` (19)
- week 8: `initialize_session_state` (83), `render_sidebar` (25),
  `solve_market` (25), `solve_optimal_dc_power_flow` (43),
  `calculate_market_dc_power_flow` (74)

## Design

### Layout

```
experiments/
  market_equilibrium.py        # def render(): this experiment's UI and the
  consumer_model.py            #   helpers only it uses
  ...                          # 25 files, content-named
  _kit/
    dispatch.py                # week-7 preamble: state, generator sidebar, solve_all
    dc_network.py              # week-8 preamble: state, market solve, DC OPF
```

Two placement rules:

- A helper used by exactly one experiment lives **in** that experiment's file.
  Per the table above that is ~95% of the code, so the ordinary edit touches
  exactly one file and cannot reach another experiment.
- `_kit/` holds only code with 2+ real consumers, named for what it models,
  never for a week. An edit there can affect its consumers; the render test
  over all 25 experiments is what catches that.

The three tiny cross-experiment helpers (10–12 lines each) are copied into each
consuming file rather than promoted to `_kit/`. They are pure arithmetic and
label lookups; duplicating them buys complete isolation at negligible drift
risk, and `_kit/` stays small enough to be worth reading.

### Module contract

Every file in `experiments/` exposes:

```python
def render() -> None: ...
```

It must not call `st.set_page_config` — the hub owns page config. Files in
`_kit/` expose plain functions and are imported normally.

### Runner

`hub/runner.py` reduces to: import the module for the requested id, call
`render()`. No monkeypatching, no AST rewriting, no global lock — with each
experiment in its own module there is nothing to isolate at runtime, so
concurrent sessions stop serialising.

`hub/state.py`'s `isolate()` is kept and keyed by experiment id: separate
modules can still pick the same `st.session_state` key.

### Catalogue

`catalogue.yaml` is deleted. An experiment *is* a file in `experiments/`:
`hub/catalogue.py` globs `experiments/*.py` (skipping `_`-prefixed entries) and
takes the id from the filename stem. `sync_catalogue`'s insert/orphan logic is
unchanged — it just gets its ids from the glob.

### Deleted

- `sources/` (all six vendored files, replaced by `experiments/`)
- `scripts/sync_sources.py`, `tests/test_sources_intact.py`
- `hub/tabsurgery.py`, `tests/test_tabsurgery.py`
- `catalogue.yaml`
- the shim/lock tests in `tests/test_runner_units.py` that cover machinery that
  no longer exists
- the vendoring section of `README.md`, rewritten to describe the new layout

### Ids and the database migration

Ids become the filename stem, dropping the `w2.`-style prefix, which would
otherwise reintroduce the week grouping through the database.

| Old id | New id / filename |
|---|---|
| w2.consumer_model | consumer_model |
| w2.consumer_elasticity | consumer_elasticity |
| w2.supplier_model | supplier_model |
| w2.supplier_elasticity | supplier_elasticity |
| w2.market_equilibrium | market_equilibrium |
| w3.pool_pricing | pool_pricing |
| w3.market_power | market_power |
| w3.profit_cost_recovery | profit_cost_recovery |
| w3.interactive_clearing | interactive_clearing |
| w4.nonlinear_3d | nonlinear_optimisation_3d |
| w4.tools_comparison | modelling_tools_comparison |
| w6.strong_duality | strong_duality |
| w6.weak_duality | weak_duality |
| w6.duality_theorems | duality_theorems |
| w7.generator_setup | dispatch_generator_setup |
| w7.comparison_results | dispatch_comparison |
| w7.detailed_analysis | dispatch_detailed_analysis |
| w7.individual_generators | dispatch_individual_generators |
| w7.pareto | dispatch_pareto_frontier |
| w8.market_setup | auction_market_setup |
| w8.network_topology | auction_network_topology |
| w8.market_results | auction_market_results |
| w8.dc_opf_results | dc_opf_results |
| w8.market_vs_opf | auction_vs_dc_opf |
| w8.theory | power_flow_theory |

Names that were only meaningful inside their week (`theory`, `market_setup`,
`detailed_analysis`) take a domain prefix — `dispatch_`, `auction_` — naming
what they model, not when they are taught.

`experiment.experiment_id` is the primary key and `event.experiment_id` is
stamped on every analytics row. Letting the ids change without a migration
would orphan all 25 configured rows (losing titles, blurbs, topic assignments,
ordering, enabled flags) and detach the analytics history. So:

`scripts/migrate_experiment_ids.py` holds the map above literally and, in one
transaction, `UPDATE`s `experiment.experiment_id` and `event.experiment_id`
old → new. It is idempotent (rows already migrated are skipped), reports any id
it does not recognise instead of touching it, and supports `--dry-run`.

### Verification

Faithfulness of a 25-file extraction is the main risk, so it is checked
directly:

1. **Baseline.** Before any change, render every experiment through
   `AppTest` and record its output — element counts by type and the rendered
   markdown/text — to `tests/baseline_render.json`, committed.
2. **Per-experiment diff.** Each experiment is extracted one at a time and its
   post-split output compared against its own baseline entry. Identical output
   means the extraction was faithful.
3. **Permanent check.** `tests/test_experiments_render.py` stays, retargeted at
   the new modules, so "all 25 render and produce output" remains enforced.

Where an experiment's output legitimately differs — weeks 7 and 8 no longer
render a shared sidebar once per file — the difference is recorded in the plan
with its reason rather than silently accepted.

## Accepted trade-off

Weeks 7 and 8 today render one sidebar and run one solve for the whole file,
shared by their five/six tabs. After the split each experiment calls the same
`_kit` module itself, so output is unchanged but the solve runs per experiment
page rather than once per file. Slightly more compute per page view, in
exchange for the experiments being genuinely independent. Accepted.
