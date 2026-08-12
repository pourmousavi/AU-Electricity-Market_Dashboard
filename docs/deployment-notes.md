# Deployment notes

How this site is hosted, what it needs, and the one security property that
rests on a human decision rather than on code.

See `README.md` for what the project is and how to work on it locally.

---

## 1. Neon Postgres

The database holds two things: the **presentation layer** (topics, which
experiment sits where, what is switched on) and the **anonymous analytics**.
It is not a cache — losing it loses the coordinator's arrangement of the
course, though not the experiments themselves, which live in `catalogue.yaml`
and `sources/`.

1. Create a project at <https://neon.tech> (the free tier is ample: this is
   tens of thousands of small rows per semester).
2. Create a database — `electricity_market_hub` is a reasonable name.
3. Copy the connection string and rewrite the scheme for SQLAlchemy +
   psycopg 3:

   ```
   postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
   ```

   Neon hands you a `postgresql://…` URL. The `+psycopg` is required —
   without it SQLAlchemy reaches for psycopg2, which is not installed.
   `sslmode=require` is not optional; Neon rejects plaintext.
4. Nothing else to do. `db.bootstrap()` creates the tables on first boot,
   `db.seed_initial()` populates the six week topics with every experiment
   enabled, and `db.reconcile()` syncs the catalogue on every boot after that.
   All three are idempotent.

Neon's free tier suspends an idle compute. The first request after a
suspension takes a few seconds to wake it; `create_engine(..., pool_pre_ping=True)`
in `hub/db.py` is what stops that showing up as a stale-connection error.

**Back it up before each semester.** A `pg_dump` of `topic` and `experiment`
is the coordinator's whole arrangement, and `delete_topic` is not reversible
from inside the app.

---

## 2. The three secrets

All three live in `.streamlit/secrets.toml` locally (gitignored) and in the
Streamlit Community Cloud **Settings → Secrets** box in production. There is
no fallback for any of them: the app will not start without `neon.dsn`, the
admin panel cannot be entered without `admin.password`, and analytics cannot
record a session without `analytics.ip_salt`.

```toml
[neon]
dsn = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require"

[admin]
password = "..."      # see section 3 — this one is load-bearing

[analytics]
ip_salt = "..."       # 32+ random characters, generated once, never rotated casually
```

`ip_salt` is what makes the stored visitor hash non-reversible. Raw IPs are
never written to the database and never logged (`hub/analytics.py`); only
`sha256(salt + ":" + ip)` is stored. Two consequences worth knowing:

* if the salt leaks, the hashes become brute-forceable — the IPv4 space is
  small enough to enumerate — so treat it exactly like a password;
* if you *change* the salt, every previously recorded visitor becomes a new
  visitor, so the unique-visitor count jumps. Rotate only deliberately, and
  note the date.

Never commit any of these. `.streamlit/secrets.toml` is in `.gitignore`;
`.streamlit/secrets.toml.example` is the committed template and must stay
empty of real values.

---

## 3. The admin password must be high-entropy — this is the actual control

**Use 20+ random characters from a password manager. Not a passphrase you
invented, not the course code, not the year.**

This is a requirement, not a suggestion, because of how the lockout works.
`hub/admin_auth.py` counts failed attempts in `st.session_state` and locks out
after 5 for 15 minutes. Streamlit's session state is **per browser session**:

* the counter is not shared between browsers, tabs, or machines;
* **reloading the page starts a new session and resets the counter to zero**;
* an attacker scripting requests never accumulates a count at all.

So the lockout is a courtesy that stops a coordinator fat-fingering their own
password five times. It is **not** a brute-force control, and it must not be
mistaken for one. The 1-second delay per attempt is likewise a speed bump, not
a barrier.

What actually protects the admin panel is the entropy of the password itself.
20 random alphanumerics is ~119 bits, which is not guessable at any rate an
attacker can achieve against a Streamlit app. A memorable phrase is not.

Behind that gate: every student's usage history, the full event export, and
the ability to switch the whole course site off. There is no rate limiting at
the platform level and no second factor.

If you would prefer a real lockout, it has to be server-side and shared —
a `failed_attempt` table in Neon keyed by hashed IP, with the check before the
password comparison. Until that exists, the password is the control.

---

## 4. Streamlit Community Cloud

1. Push to GitHub. The repository may be public — it contains no secrets, and
   `sources/` is vendored from repositories that are already published.
2. At <https://share.streamlit.io>, **New app**, point it at the repository,
   branch `main`, main file `app.py`.
3. **Advanced settings → Python version: 3.12.**
4. Paste the three secrets from section 2 into the Secrets box. They are
   available as `st.secrets` immediately; editing them restarts the app.
5. Deploy. First boot creates the tables and seeds the six topics.

### Things that will bite you

**`requirements.txt` is reinstalled on every rebuild, and it is pinned for a
reason.** `streamlit>=1.55,<1.62`:

* below 1.55, `st.expander` and `st.tabs` do not accept `key`, and the admin
  panel dies with a `TypeError` while the student site looks perfectly fine —
  a failure mode nobody notices until the coordinator tries to change
  something. 1.55.0 is the first release that accepts it (checked against the
  published wheels; 1.54.0 does not), and
  `tests/test_admin.py::test_installed_streamlit_supports_the_admin_panels_api`
  fails loudly if an environment drops below it;
* from 1.62, `use_container_width` is expected to be gone. The hub itself has
  migrated to `width="stretch"`, but the six vendored dashboards still use
  `use_container_width` and **must not be edited**. Lifting the ceiling means
  re-vendoring from upstream first, then running
  `pytest tests/test_experiments_render.py`.

Do not replace the range with an unpinned `streamlit`. A Community Cloud
rebuild is triggered by any push, and an unpinned upper bound means the site
can break with no change of ours.

**Error details are suppressed.** `.streamlit/config.toml` sets
`client.showErrorDetails = "none"`. The default is `"full"`, which puts the
exception, absolute deployment paths and a source excerpt on a page that any
anonymous student can reach. `hub/pages_experiment.py` already catches render
failures and routes them to the server log and an `experiment_error` analytics
event; this setting is the backstop for anything raised outside that block.
Leave it off. To debug a real failure, read the Community Cloud logs — the
traceback is there in full.

**Resource limits.** The free tier gives roughly 1 GB of RAM. The week 7 and
week 8 experiments run PyPSA and cvxpy solves that can take several seconds
and hold real memory. A full tutorial cohort hitting solver-backed experiments
at once is the load case to watch; if the app starts restarting under load,
that is where to look first.

---

## 5. The unique-visitor metric labels itself

The Usage tab's first metric is titled by `analytics.identity_label()`, which
is evaluated **at runtime from `st.context.headers`** and is never hardcoded:

* if the platform forwards a client IP (`x-forwarded-for` / `x-real-ip`), the
  metric counts distinct salted IP hashes and reads **"Unique IPs"**;
* if it does not, the app falls back to an anonymous device id in the URL
  query string and the metric reads **"Unique devices"** instead.

There is nothing to configure, and nothing to change if the platform's
behaviour changes — whether a host forwards a client IP is a deployment fact,
not a code fact, so the label follows the deployment. The caption under the
metrics points here.

The practical difference: "Unique devices" undercounts a student who clears
their history or opens the site on their phone and laptop, and it cannot
distinguish two students sharing one machine. Neither figure is a headcount.
Read both as trend indicators for which material gets used, which is all they
were built for.
