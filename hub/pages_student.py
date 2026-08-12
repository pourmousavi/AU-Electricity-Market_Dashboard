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


def _rows(items: list, per_row: int) -> list[list]:
    return [items[i:i + per_row] for i in range(0, len(items), per_row)]


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

    # One st.columns() call per row, not one for the whole grid: columns only
    # stretch to the height of the tallest card in *their own* row, so a single
    # grid-wide call would stack cards down each column with nothing to align to.
    for row in _rows(cards, 3):
        for column, (topic, is_open, chip) in zip(st.columns(3, gap="medium"), row):
            with column:
                st.markdown(
                    f"""<div class="hub-card {'' if is_open else 'locked'}">
  <span class="hub-chip {'open' if is_open else ''}">{_esc(chip)}</span>
  <h3>{_esc(topic['name'])}</h3>
  <p>{_esc(topic['subtitle'])}</p>
</div>""",
                    unsafe_allow_html=True,
                )
                label = "Open" if is_open else "Preview"
                if st.button(
                    label, key=f"_hub.card_{topic['id']}", width="stretch"
                ):
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
    for row in _rows(available, 2):
        for column, exp in zip(st.columns(2, gap="medium"), row):
            with column:
                st.markdown(
                    f"""<div class="hub-card">
  <h3>{_esc(exp['title'])}</h3>
  <p>{_esc(exp['blurb'])}</p>
</div>""",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Open experiment", key=f"_hub.exp_{exp['experiment_id']}",
                    width="stretch",
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
