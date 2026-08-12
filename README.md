# Electricity Market & Power Systems Operation — dashboard hub

ELEC ENG 4087/7087, University of Adelaide.

One public Streamlit site that presents **25 interactive experiments** drawn
from **six pre-existing weekly dashboards**. Students get a card grid of
topics; the coordinator turns individual experiments on as the course
progresses, without a redeploy.

There is no student login. There is a password-gated admin panel for the
coordinator, and anonymous usage analytics in Neon Postgres.

---

## An experiment is a module

Each of the 25 experiments is a Python module in `experiments/` exposing a
single `render()` function that draws it. There is nothing to isolate at
runtime: no monkeypatching of the shared `streamlit` module, no process-wide
lock, no AST surgery. `hub/runner.py` just imports the module and calls
`render()`.

The reason this shape is worth keeping intact: code used by exactly one
experiment lives in that experiment's own file — roughly 95% of the
codebase — so the ordinary edit ("fix an axis label in week 7's generator
setup") touches one file and structurally cannot reach any other experiment.

A few page bodies are shared by construction, because the original bundled
dashboards drew several tabs from one continuous script. `experiments/_kit/`
holds exactly the three that have 2+ real consumers:

| `_kit` module | shared by |
|---|---|
| `duality.py` | 3 experiments |
| `dispatch.py` | 5 experiments |
| `dc_network.py` | 6 experiments |

Each exposes `page(tab_body=None)`. The calling experiment passes its own tab
body in, and `page()` invokes it at exactly the point the original `st.tabs`
block would have rendered that tab, so render order still matches the
bundled original.

Modules that share a `_kit` page also declare `STATE_GROUP` — `"duality"`,
`"dispatch"`, or `"dc_network"` — which is how `hub/runner.py` knows those
modules deliberately share Streamlit session state (see `hub/state.py`). A
module with no `STATE_GROUP` is its own state group, keyed by its own id, and
cannot collide with anything else.

One rule with no exceptions: **no module may call `st.set_page_config`.**
`app.py` is the only place that does — Streamlit raises if it is called
twice in one script run, so a second call anywhere else takes down the page.

### The id is the database key

An experiment's id is its filename stem (`dispatch_pareto_frontier.py` →
`dispatch_pareto_frontier`), and that id doubles as the primary key of the
`experiment` table in Postgres — it's baked into the shareable URL
(`?view=experiment&exp=…`) and into every analytics row. Renaming a file
therefore means renaming a live database key, which `hub/db.py::reconcile`
cannot do by itself: on its own it only knows how to insert a newly-seen id
or flag a disappeared one as orphaned, never that "id A became id B". Do that
with a one-off migration instead; `scripts/migrate_experiment_ids.py` is the
worked example, from the migration this project's own split required.

---

## Two layers of configuration

Keep these straight; almost every "where do I change X" question resolves to
one of them.

| | `experiments/` (in the repo) | Database (edited live) |
|---|---|---|
| Answers | **which** experiments exist | **how** to present each one |
| Holds | one module per experiment, each exposing `render()` | topic, title, blurb, order, enabled |
| Changed by | a commit and a redeploy | the admin panel, instantly |
| Owner | whoever maintains the code | the course coordinator |

An experiment that is a module in `experiments/` but has no database row is
created on next boot — **unassigned and disabled**, so nothing reaches
students until it is deliberately placed. An experiment whose module
disappears from `experiments/` is flagged `orphaned`, never deleted, so its
settings survive a rename or a temporary removal. That reconciliation is
`hub/db.py::reconcile`.

---

## The admin panel

Append `?admin=1` to the site URL. One shared password, from deployment
secrets (see `docs/deployment-notes.md` — read the section on password
entropy before choosing one).

Three tabs:

* **Usage** — unique visitors, sessions, experiment opens, and a ranking of
  which experiments students actually open and for how long. The unique-visitor
  metric labels itself ("Unique IPs" vs "Unique devices") according to what
  the deployment can really measure.
* **Content** — the tab that matters day to day. Create and rename topics,
  move any experiment to any topic, set the order, and switch experiments and
  whole topics on and off. Disabling a topic closes every experiment in it,
  including direct URLs.
* **Export** — the raw event log as CSV.

Analytics are anonymous by construction: no account, name or email, and no raw
IP is ever stored or logged — only a salted one-way hash. See `hub/analytics.py`.

---

## Adding a new experiment

1. Drop a `.py` file exposing `render()` into `experiments/`. That's the
   whole mechanical step — there is no registry or catalogue file to edit;
   `hub/catalogue.py` globs `experiments/*.py` at startup and the filename
   stem becomes the id. Pick that filename carefully: it's the id for the
   rest of this experiment's life (see "The id is the database key" above).
   Remember the one hard rule — it must not call `st.set_page_config`.
2. If the experiment is meant to share session state with others (typically
   because it draws through a shared `experiments/_kit/` page), declare a
   matching `STATE_GROUP` on the module. Otherwise leave `STATE_GROUP` unset
   and it gets its own isolated state, keyed by its own id.
3. Run the render smoke test, which executes every module in `experiments/`:

   ```bash
   .venv/bin/python -m pytest tests/test_experiments_render.py
   ```
4. Commit and push. The new experiment arrives **unassigned and disabled** —
   go to `?admin=1` → Content, put it in a topic, and switch it on when the
   week arrives.

---

## Local development

Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in the three secrets; for local work a file-backed SQLite DSN is fine:
#   dsn = "sqlite:///local_hub.db"

.venv/bin/python -m streamlit run app.py
```

`.streamlit/secrets.toml` is gitignored and must stay that way. Never commit a
DSN, a password or the analytics salt.

Tests:

```bash
.venv/bin/python -m pytest -q
```

Two tests carry most of the weight:

* `tests/test_extraction_faithful.py`, checked against
  `tests/baseline_render.json` — the recorded text every experiment rendered
  as part of the six bundled dashboards, captured before the split. It pins
  every experiment's rendered text against that record, so a change that
  quietly alters what students see fails here even if nothing crashes.

  Which means a *deliberate* wording change fails it too. That is intended —
  it asks you to confirm. Re-record rather than editing the JSON by hand:

  ```bash
  .venv/bin/python scripts/refresh_baseline.py --check   # what would change
  .venv/bin/python scripts/refresh_baseline.py           # accept it
  ```

  Read the resulting diff before committing: every line it changes is a line
  a student would have seen change. Note that refreshing replaces the
  pre-split record with current behaviour — the original stays in git history.
* `tests/test_experiments_render.py` — imports and renders all 25 experiments
  and additionally asserts that none leaks a former sibling's content (the
  failure mode a shared `_kit` page or a copy-paste extraction mistake would
  produce).

### Layout

```
app.py                  entry point; the only place st.set_page_config is called
experiments/            one module per experiment, each exposing render()
  _kit/                 page bodies shared by 2+ experiments (duality, dispatch, dc_network)
hub/
  runner.py             imports one experiment module and calls its render()
  catalogue.py          globs experiments/*.py; filename stem is the experiment id
  db.py                 topics, experiment placement, analytics tables
  router.py             ?view= query-string routing and the sidebar nav
  pages_student.py      home grid, topic page, locked teaser
  pages_experiment.py   access control, dwell tracking, then the dashboard
  admin.py              usage / content / export
  admin_auth.py         the coordinator password gate
  analytics.py          anonymous capture (salted IP hash, never the raw IP)
  queries.py            read-side analytics for the admin panel
  state.py              drops experiment state when the STATE_GROUP changes; same-group experiments keep theirs
  theme.py              hub CSS, scoped to .hub- classes only
docs/deployment-notes.md  Neon, secrets, Community Cloud
```

Two conventions the tests rely on:

* every hub-owned session-state key and widget key is prefixed `_hub.` — that
  prefix is what tells `hub/state.py` which keys belong to an experiment
  module and may be cleared;
* the hub's dark CSS is scoped to `.hub-` classes, so it cannot leak into an
  experiment module's own styling.
