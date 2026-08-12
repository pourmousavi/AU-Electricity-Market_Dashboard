# Electricity Market & Power Systems Operation — dashboard hub

ELEC ENG 4087/7087, University of Adelaide.

One public Streamlit site that presents **25 interactive experiments** drawn
from **six pre-existing weekly dashboards**. Students get a card grid of
topics; the coordinator turns individual experiments on as the course
progresses, without a redeploy.

There is no student login. There is a password-gated admin panel for the
coordinator, and anonymous usage analytics in Neon Postgres.

---

## The one rule: `sources/` is vendored verbatim

The six weekly dashboards under `sources/` are **byte-for-byte copies of their
upstream repositories**. They are never edited, reformatted, or "tidied" — not
for a lint error, not for a deprecation warning, not to make an experiment
easier to isolate. Everything the hub needs is achieved from the outside.

Two things enforce this:

* `tests/test_sources_intact.py` re-downloads each upstream file and fails if
  the vendored copy differs.
* `scripts/sync_sources.py` is the **only** sanctioned way to change anything
  under `sources/`:

  ```bash
  .venv/bin/python scripts/sync_sources.py --dry-run   # what would change
  .venv/bin/python scripts/sync_sources.py             # pull upstream
  .venv/bin/python -m pytest tests/test_experiments_render.py
  ```

  Re-running the render test after a sync is not optional: an upstream edit
  that renames a tab label or a sidebar option silently breaks the experiment
  that pins it, and the catalogue is the only place that knows.

Why this matters: the dashboards keep being developed upstream. The moment we
patch a vendored file by hand, the next sync either clobbers the patch or
conflicts with it, and the site's behaviour stops being traceable to anything.

### How isolation works instead

`hub/runner.py` executes a vendored file unmodified and makes exactly one
experiment's branch run, in one of two modes declared per experiment in
`catalogue.yaml`:

* **`pin_selectbox`** (weeks 2, 3, 4) — the module calls
  `st.sidebar.selectbox` once at module level and dispatches on the result.
  The runner makes that one call return the experiment we want.
* **`pin_tab`** (weeks 6, 7, 8) — content is built inline inside `with tabN:`
  blocks, so calling a render function is not enough. `hub/tabsurgery.py`
  blanks the unselected tab bodies in the AST and the runner patches
  `st.tabs` to draw a single tab.

Both modes patch the process-global `streamlit` module, so
`render_experiment` holds a module-level lock for the whole patched block and
each shim additionally checks it is being called by the thread that installed
it. Streamlit runs one thread per session with no global script lock, and the
patched window spans an entire PyPSA or cvxpy solve — concurrent students are
the normal case, not a rare race. Do not remove either defence.

---

## Two layers of configuration

Keep these straight; almost every "where do I change X" question resolves to
one of them.

| | `catalogue.yaml` (in the repo) | Database (edited live) |
|---|---|---|
| Answers | **How** to render an experiment | **How** to present it |
| Holds | source file, mode, selector, entry point | topic, title, blurb, order, enabled |
| Changed by | a commit and a redeploy | the admin panel, instantly |
| Owner | whoever maintains the code | the course coordinator |

An experiment that is in `catalogue.yaml` but has no database row is created
on next boot — **unassigned and disabled**, so nothing reaches students until
it is deliberately placed. An experiment whose id disappears from
`catalogue.yaml` is flagged `orphaned`, never deleted, so its settings survive
a rename or a temporary removal. That reconciliation is `hub/db.py::reconcile`.

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

## Adding a new dashboard

1. Drop the `.py` file into `sources/` **unmodified**, and add it to
   `SOURCES` in `scripts/sync_sources.py` so it stays in sync with upstream.
2. Add the file under `sources:` in `catalogue.yaml`, then one entry per
   experiment under `experiments:`:

   ```yaml
   - {id: w9.my_experiment, source: week9, mode: pin_tab, entry: main, selector: "📊 My Tab"}
   ```

   * `id` — stable and unique; it is the shareable URL (`?view=experiment&exp=…`)
     and the analytics key, so renaming one orphans its history.
   * `mode` — `pin_selectbox` or `pin_tab`, matching how the file is built.
   * `selector` — the sidebar option label or the tab label, **exactly** as it
     appears in the source, emoji included.
   * `entry` — `module` if the content runs at import, `main` if the file
     defines `main()` and calls it under a `__main__` guard.
3. Run the render smoke test, which executes every catalogued experiment:

   ```bash
   .venv/bin/python -m pytest tests/test_experiments_render.py
   ```
4. Commit and push. The new experiments arrive **unassigned and disabled** —
   go to `?admin=1` → Content, put them in a topic, and switch them on when
   the week arrives.

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

`tests/test_sources_intact.py` needs the `gh` CLI authenticated, since it
checks the vendored copies against upstream.

### Layout

```
app.py                  entry point; the only place st.set_page_config is called
catalogue.yaml          how to render each experiment
hub/
  runner.py             executes a vendored file, isolating one experiment
  tabsurgery.py         AST surgery for pin_tab sources
  catalogue.py          loads and validates catalogue.yaml
  db.py                 topics, experiment placement, analytics tables
  router.py             ?view= query-string routing and the sidebar nav
  pages_student.py      home grid, topic page, locked teaser
  pages_experiment.py   access control, dwell tracking, then the dashboard
  admin.py              usage / content / export
  admin_auth.py         the coordinator password gate
  analytics.py          anonymous capture (salted IP hash, never the raw IP)
  queries.py            read-side analytics for the admin panel
  state.py              stops the six dashboards corrupting each other's state
  theme.py              hub CSS, scoped to .hub- classes only
docs/deployment-notes.md  Neon, secrets, Community Cloud
```

Two conventions the tests rely on:

* every hub-owned session-state key and widget key is prefixed `_hub.` — that
  prefix is what tells `hub/state.py` which keys belong to a vendored module
  and may be cleared;
* the hub's dark CSS is scoped to `.hub-` classes, so it cannot leak into a
  vendored dashboard's own styling.
