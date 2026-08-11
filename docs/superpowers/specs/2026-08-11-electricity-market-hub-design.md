# Electricity Market Course — Unified Dashboard Hub

**Date:** 2026-08-11
**Author:** Ali Pourmousavi Kani (with Claude)
**Target repo:** `github.com/pourmousavi/AU-Electricity-Market_Dashboard` (private, currently empty)
**Course:** ELEC ENG 4087/7087 — Electricity Market and Power Systems Operation

---

## 1. Purpose

Collate six standalone Streamlit teaching dashboards into one free-hosted site for students,
with per-experiment access control and usage analytics for the instructor.

**Hard constraint:** the content of the six existing dashboards must not change. Their source
files are vendored byte-for-byte and driven from outside via a rendering shim.

### Success criteria

1. One public URL students can visit; no login.
2. All 25 experiments reachable, rendering identically to their current standalone dashboards.
3. Instructor can assign any experiment to any topic, reorder, and toggle it on/off from an
   admin panel, with the change live immediately and no redeploy.
4. Instructor can see unique visitors, sessions, per-experiment opens and dwell time.
5. Free hosting, free data store.
6. Adding or removing a whole dashboard requires only dropping a file in and editing one YAML.

---

## 2. Source material (verified)

Six repos, each a single self-contained `.py` file. No data files, no `open()`, no `read_csv` —
all data is generated in code. Four repos also contain a committed virtualenv (~500 MB total)
which is **not** carried across.

| Repo | File | Lines | Structure |
|---|---|---|---|
| `...Consumer-Supplier-Model-Elasticity-and-Equilibrium` | `Dashboard_Week2.py` | 2002 | one top-level `st.sidebar.selectbox` → 5 `*_section()` functions |
| `...Pricing-marketPower-profitCostRecovery-bidding` | `Dashboard_Week3.py` | 2064 | one top-level `st.sidebar.selectbox` → 4 `*_section()` functions |
| `...Basic-Def-Optimisation-Tools-Comparison` | `Dashboard_Week4.py` | 1221 | one top-level `st.sidebar.selectbox` → 2 inline branches |
| `...Duality-Theory` | `Dashboard_Week6.py` | 544 | module-level `st.tabs` with inline bodies |
| `...ED-VIU` | `Dashboard-week7.py` | 1698 | `main()` under `__main__` guard; 5 tabs, each a single `render_*()` call |
| `...PF-double-sided-auction` | `Dashboard-Week8.py` | 2715 | `main()` under `__main__` guard; 6 tabs, each a single `render_*()` call |

Combined dependencies: `streamlit, pandas, numpy, plotly, scipy, sympy, matplotlib, cvxpy,
networkx, pypsa`.

### Known properties that shape the design

- **All six call `st.set_page_config()` at import.** Streamlit permits one call per app, and it
  must precede other output. The shim no-ops subsequent calls.
- **Weeks 2/3/4 call `st.sidebar.selectbox` exactly once** (the nav dropdown). Inner dropdowns are
  `st.selectbox` in the main area and are never intercepted.
- **Weeks 7/8 are guarded by `if __name__ == "__main__"`,** so importing them executes nothing;
  `main()` must be called explicitly. **Week 6 has no guard** — its content runs at module level.
- **Tab bodies are not uniformly functions.** Most of Weeks 7/8's tabs are a single
  `render_*()` call, but Week 7's "Generator Setup" tab is `render_generator_table()` *plus* ~40
  inline lines (setup metrics, demand-profile plot), Week 8's "Theory & Concepts" tab is ~110 lines
  of inline markdown, and all three of Week 6's tabs are inline. Calling render functions is
  therefore not a sufficient isolation mechanism — it would silently drop content.
- **Content before the tab bar is shared context.** Weeks 7/8 render a header, learning objectives
  and the sidebar in `main()` before `st.tabs`; Week 6 renders its primal/dual solver and 3D plot
  before its tabs. This shared preamble renders for every experiment drawn from that module, which
  is desirable — it gives each experiment its setup controls.
- **Three session-state keys collide across modules:** `generators`, `supply_bids`, `demand_bids`.
- **All modules hardcode light-coloured CSS boxes** (`background-color: white`, `#f0f8ff`,
  `#f8f9fa`) with default text colour. A global dark theme would render light text on light
  boxes and break readability.

---

## 3. Asset inventory — 25 experiments

| ID | Display name | Source | Mode | Selector / tab label |
|---|---|---|---|---|
| `w2.consumer_model` | Consumer Model | week2 | `pin_selectbox` | `Consumer Model` |
| `w2.consumer_elasticity` | Consumer Elasticity | week2 | `pin_selectbox` | `Consumer Elasticity` |
| `w2.supplier_model` | Supplier Model | week2 | `pin_selectbox` | `Supplier Model` |
| `w2.supplier_elasticity` | Supplier Elasticity | week2 | `pin_selectbox` | `Supplier Elasticity` |
| `w2.market_equilibrium` | Market Equilibrium | week2 | `pin_selectbox` | `Market Equilibrium` |
| `w3.pool_pricing` | Pool Market Pricing | week3 | `pin_selectbox` | `Pool Market Pricing` |
| `w3.market_power` | Market Power Analysis | week3 | `pin_selectbox` | `Market Power Analysis` |
| `w3.profit_cost_recovery` | Profit & Cost Recovery | week3 | `pin_selectbox` | `Profit & Cost Recovery` |
| `w3.interactive_clearing` | Interactive Market Clearing | week3 | `pin_selectbox` | `Interactive Market Clearing` |
| `w4.nonlinear_3d` | 3D Nonlinear Optimization | week4 | `pin_selectbox` | `3D Nonlinear Optimization` |
| `w4.tools_comparison` | Modelling Tools Comparison | week4 | `pin_selectbox` | `Modelling Tools Comparison` |
| `w6.strong_duality` | Strong Duality | week6 | `pin_tab` | `Strong Duality` |
| `w6.weak_duality` | Weak Duality Cases | week6 | `pin_tab` | `Weak Duality Cases` |
| `w6.duality_theorems` | Duality Theorems | week6 | `pin_tab` | `Duality Theorems` |
| `w7.generator_setup` | Generator Setup | week7 | `pin_tab` | `🏭 Generator Setup` |
| `w7.comparison_results` | ED Comparison Results | week7 | `pin_tab` | `📊 Comparison Results` |
| `w7.detailed_analysis` | ED Detailed Analysis | week7 | `pin_tab` | `🔍 Detailed Analysis` |
| `w7.individual_generators` | Individual Generators | week7 | `pin_tab` | `📈 Individual Generators` |
| `w7.pareto` | Pareto Frontier | week7 | `pin_tab` | `🎯 Pareto Frontier` |
| `w8.market_setup` | Market Setup | week8 | `pin_tab` | `🏪 Market Setup` |
| `w8.network_topology` | Network Topology | week8 | `pin_tab` | `🔌 Network Topology` |
| `w8.market_results` | Market Results | week8 | `pin_tab` | `📈 Market Results` |
| `w8.dc_opf_results` | DC OPF Results | week8 | `pin_tab` | `⚡ DC OPF Results` |
| `w8.market_vs_opf` | Market vs DC OPF | week8 | `pin_tab` | `🔋 Market vs DC OPF` |
| `w8.theory` | Theory & Concepts | week8 | `pin_tab` | `📚 Theory & Concepts` |

Every one of these 25 is **individually assignable to any topic and individually toggleable**.
Experiments originating from different source dashboards may be grouped on the same topic card.

---

## 4. Architecture

### 4.1 Two-layer configuration

Configuration is split by ownership. This is the central design decision.

**`catalogue.yaml`** — committed to the repo, describes only *how to render* an experiment.
Changes rarely, requires a redeploy.

```yaml
sources:
  week2: sources/week2_consumer_supplier.py
  week7: sources/week7_ed_viu.py

experiments:
  - id: w2.consumer_model
    source: week2
    mode: pin_selectbox
    selector: "Consumer Model"

  - id: w7.pareto
    source: week7
    mode: pin_tab
    selector: "🎯 Pareto Frontier"
    entry: main          # call main() after executing the module

  - id: w6.strong_duality
    source: week6
    mode: pin_tab
    selector: "Strong Duality"
    entry: module        # content runs at module level; nothing to call
```

**Postgres `experiment` / `topic` tables** — describe *how to present* an experiment. Edited live
in the admin panel, effective immediately, no redeploy.

| Field | Purpose |
|---|---|
| `experiment_id` | FK to catalogue id |
| `topic_id` | which card it appears on (nullable = unassigned) |
| `title` | instructor-editable display name |
| `blurb` | one or two lines shown on the tile |
| `sort_order` | position within the topic |
| `enabled` | on/off toggle |

`topic` holds `id, name, subtitle, sort_order, enabled, unlock_message`.

**Initial seed (first deploy only):** six topics are created — Week 2, 3, 4, 6, 7, 8 — with all 25
experiments assigned to the topic matching their source dashboard, in their current order, and
**enabled**. The instructor then disables whatever has not been taught yet from one screen of
toggles, and rearranges from there.

**Ongoing reconciliation (every startup):** catalogue ids that are new since the last run are
inserted as *unassigned and disabled*, so nothing appears to students until deliberately placed.
DB rows whose catalogue id has disappeared are marked orphaned — hidden from students, still
listed in admin, so nothing vanishes silently.

### 4.2 Rendering shim — `hub/runner.py`

One module, two modes, no edits to vendored sources. Both modes guarantee that **only the selected
experiment's code executes** — unselected content is never computed and never reaches the browser.

**Global:** `st.set_page_config` is replaced with a no-op for the duration of a vendored module's
execution (the hub calls the real one first).

**`pin_selectbox`** — Weeks 2, 3, 4.
Temporarily replace `st.sidebar.selectbox` with a function that returns the configured `selector`
value on its **first** call and restores the original immediately after, then execute the source
file. These modules call it exactly once at top level and dispatch with `if page == ...`, so
exactly one page's code path runs. Output is identical to the standalone dashboard on that page.

**`pin_tab`** — Weeks 6, 7, 8.
Tab bodies contain inline code, so calling render functions is not sufficient. Instead the source
is transformed **in memory** at load time via Python's `ast` module — the file on disk is never
modified:

1. Parse the source. Find the `Assign` node whose value is a call to `st.tabs`, read the tuple of
   target names (`tab1, tab2, tab3`) and the literal label list, and map label → target name.
2. Find every `With` node whose sole context expression is one of those names. For every name that
   is **not** the selected experiment, replace the body with `ast.Pass()`.
3. Compile and execute the transformed tree. At runtime `st.tabs` is monkeypatched to call the real
   `st.tabs` with only the selected label and return a list where the selected position holds the
   real container and every other position holds a `contextlib.nullcontext()` — those positions are
   only ever entered by a `pass` body.
4. If `entry: main`, call `main()`; if `entry: module`, module-level execution has already done it.

The result is that the module's shared preamble (header, learning objectives, sidebar controls)
renders exactly as today, followed by the one selected tab's content, with a single tab header.
Unselected tabs are not executed — so Week 8's DC OPF solve does not run when a student is reading
the Theory tab, and disabled experiments are never computed.

Transformed code objects are cached per `(source, experiment_id)` in `st.cache_resource`, so the
AST work happens once per experiment per app boot.

**Failure mode:** if a source dashboard is later restructured so the expected `st.tabs` assignment
or `with tabN:` pattern is absent, the transform raises rather than silently rendering the wrong
content. The smoke test in §9 catches this before deploy.

### 4.3 Session-state isolation

Vendored modules share one Streamlit session and three key names collide (`generators`,
`supply_bids`, `demand_bids`). Before running an experiment, the hub snapshots
`set(st.session_state)`. On switching to an experiment from a **different source module**, keys
created by the previous module are deleted. Hub-owned keys are namespaced `_hub.*` and never
cleared. Switching between experiments from the *same* module preserves state, matching how the
standalone dashboards behave today.

### 4.4 Repository layout

```
app.py                      # entry point: page config, theme, router
catalogue.yaml
hub/
  router.py                 # st.navigation wiring, breadcrumb, prev/next
  home.py                   # topic card grid
  topic.py                  # experiment tiles within a topic
  experiment.py             # chrome + runner invocation + dwell tracking
  locked.py                 # teaser page for disabled content
  admin.py                  # password gate + usage/content/export tabs
  runner.py                 # the three isolation modes
  db.py                     # Neon connection, schema bootstrap, queries
  analytics.py              # event capture + batched writes
  theme.py                  # scoped CSS for dark hub chrome
sources/
  week2_consumer_supplier.py    # vendored verbatim
  week3_pricing_market_power.py
  week4_optimisation_tools.py
  week6_duality.py
  week7_ed_viu.py
  week8_pf_auction.py
scripts/
  sync_sources.py           # re-pull latest from the six upstream repos
tests/
  test_experiments_render.py    # AppTest smoke test over all 25
requirements.txt
.streamlit/config.toml
```

`sources/` files are **never edited**. `scripts/sync_sources.py` re-downloads each from its
upstream repo via the GitHub API and reports any change that breaks the smoke test.

---

## 5. Navigation and visual design

### 5.1 Structure

```
Home (topic card grid)
  └─ Topic page (experiment tiles)
       └─ Experiment page (hub chrome + vendored content)
  └─ Locked teaser page
Admin (password-gated, not linked from student UI)
```

Sidebar carries hub navigation (Home, topic list, experiments in the current topic), a divider,
then the vendored module's own controls beneath it. Vendored sidebar content is unchanged.

### 5.2 Visual direction

Adelaide-inspired but not official branding: no university logo, no brand sign-off required.

- Base: deep navy `#0B1020` to charcoal gradient
- Accent: Adelaide red `#C8102E`
- Data/highlight: electric cyan
- Motifs: animated gradient mesh, subtle transmission-grid and waveform texture
- Cards: glassmorphic, lift and glow on hover
- Type: one strong display face for headings, system stack for body

**Theme split (deliberate):** the global Streamlit theme stays **light**, because vendored modules
hardcode light backgrounds with default text colour. The dark artistic treatment is applied as
page-scoped CSS on Home, topic pages, locked pages and admin only. Experiment pages get a slim
dark header bar, then the content renders on the light theme it was built for. This is the only
way to satisfy both "flashy and modern" and "content unchanged".

### 5.3 Locked content

A disabled experiment or topic still appears, with a padlock. Clicking opens a styled teaser page
showing the title, blurb and the instructor's `unlock_message` (e.g. "Opens after the Week 6
lecture"). No interactive content is rendered.

**What is and isn't protected:** a disabled experiment's code never executes and its output never
reaches the browser — both isolation modes gate by *not running* the code, not by hiding it. What
a determined student can see is the experiment's title, blurb and unlock message, since those are
rendered on the teaser page by design. That is adequate for pacing coursework. It is not an
access-control system, and assessment material should not rely on it.

---

## 6. Analytics

### 6.1 Store

**Neon free-tier Postgres.** Chosen over Supabase (free projects pause after 7 days idle) and
Google Sheets (write-rate limits during a live lecture, 15-minute service-account setup). Sign-up
is via GitHub, the free tier does not pause or expire, and 0.5 GB is far beyond a semester of logs.

### 6.2 Schema

```sql
CREATE TABLE visitor_session (
  id            TEXT PRIMARY KEY,      -- Streamlit session id
  ip_hash       TEXT,                  -- salted SHA-256, salt in secrets
  user_agent    TEXT,
  referrer      TEXT,
  first_seen    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE event (
  id            BIGSERIAL PRIMARY KEY,
  session_id    TEXT REFERENCES visitor_session(id),
  ts            TIMESTAMPTZ DEFAULT now(),
  kind          TEXT,                  -- home_view | topic_view | experiment_open | experiment_close
  topic_id      INT,
  experiment_id TEXT,
  dwell_ms      INT                    -- populated on experiment_close
);
```

### 6.3 Capture

- Client IP read from `X-Forwarded-For` via `st.context.headers`, then salted-hashed. The raw IP
  is never written to the database.
- Events are buffered in session state and flushed as a batched insert (on flush threshold or on
  navigation), so a lecture-time click burst is one insert rather than fifty.
- Connection pooled via `st.cache_resource`.

**Risk — must be verified first.** It is not yet confirmed that Streamlit Community Cloud passes
`X-Forwarded-For` through to `st.context.headers`. Implementation step 1 is a deployed spike to
check. If unavailable, the fallback is an anonymous random ID persisted in the URL query string
(`st.query_params`), which counts unique devices rather than unique IPs. The implementation must
report which mechanism is actually active, and the admin panel must label the metric accordingly
("unique IPs" vs "unique devices") rather than silently mislabelling it.

### 6.4 Privacy

No login, no names, no raw IPs. A short privacy note on the home page states that anonymous usage
statistics are collected to improve the course material. Under the Australian Privacy Act a salted
hash with the salt held only in deployment secrets is not reasonably re-identifiable.

---

## 7. Admin panel

Reached via the query parameter `?admin=1`. The admin page is registered with `st.navigation` but
excluded from the student sidebar, so it is never linked or listed in the student UI. Gated by a
password held in `st.secrets` (never committed), compared with `hmac.compare_digest`. Authorisation
is session-scoped. After 5 failed attempts the session is locked out for 15 minutes, and every
attempt incurs a fixed 1-second delay, so the password cannot be usefully brute-forced.

- **Usage** — date-range filter; unique visitors, total sessions; a ranked table of experiments by
  opens and median dwell time (this is the "which component is most attractive" view); per-topic
  rollup; visits over time.
- **Content** — create, rename, reorder and enable/disable topics; assign any of the 23
  experiments to any topic; reorder within a topic; edit title, blurb and unlock message; toggle
  each experiment. Changes take effect on the students' next interaction.
- **Export** — CSV download of raw events and sessions.

---

## 8. Hosting

**Streamlit Community Cloud**, deployed from the private repo, free, at a chosen subdomain
(e.g. `au-electricity-market.streamlit.app`). Secrets hold the Neon connection string, the IP hash
salt and the admin password.

Cohort is under 50 students, well within the free tier. If PyPSA/CVXPY memory proves tight, the
fallback is Hugging Face Spaces (16 GB RAM free) using the same repo plus one config file; the
analytics store is external either way, so no data is affected by the move.

GitHub Pages was considered and rejected: it serves static files only and cannot run Streamlit.

---

## 9. Testing

- **`tests/test_experiments_render.py`** — uses `streamlit.testing.v1.AppTest` to load every one of
  the 25 experiments and assert no exception is raised. This is the regression check that catches a
  shim breaking when a source dashboard is updated via `sync_sources.py`.
- **Runner unit checks** — `pin_selectbox` restores the original `st.sidebar.selectbox` after the
  first call; state isolation clears foreign module keys and preserves `_hub.*` keys.
- **Analytics** — a local check that events buffer and flush, and that the same IP hashes
  identically within a run and differently across salts.

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `X-Forwarded-For` unavailable on Community Cloud | Cannot count unique IPs | Spike first; fall back to query-param device ID and relabel the metric |
| Session-state collision across modules | Crash on module switch | Snapshot-and-clear on source change; smoke test covers switching |
| PyPSA/CVXPY memory on free tier | App restarts under load | Fallback to Hugging Face Spaces, same repo |
| Upstream dashboard edited, breaks the shim | Experiment fails to render | AST transform raises loudly rather than rendering wrong content; `sync_sources.py` + AppTest smoke test before deploy |
| AST transform is coupled to the `tab1, tab2 = st.tabs([...])` / `with tabN:` pattern | `pin_tab` experiments fail | Pattern verified present in all three tab modules; transform asserts on the pattern and the smoke test covers all 25 experiments |
| Locked content: titles visible, content never executes | Low | Documented; do not use for assessment material |

---

## 11. Out of scope

- Editing the content of any of the six dashboards.
- Student accounts, verified identity, per-student progress tracking.
- Scheduled/automatic unlock dates (manual toggle only, by decision).
- Retiring the six upstream repos — they remain the sources of truth.
