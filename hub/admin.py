"""Admin panel: usage, content arrangement, export.

The content tab is the one that matters day to day — it is how experiments get
assigned to topics and switched on as the course progresses, without a redeploy.
"""
from __future__ import annotations

import streamlit as st

from hub import admin_auth, analytics, db, queries, theme
from hub.router import Route, go

NEW_TOPIC_KEYS = ("_hub.newtopic_name", "_hub.newtopic_sub", "_hub.newtopic_unlock")


def clear_new_topic_form(state) -> None:
    """Empty the "Add a new topic" inputs so the next rerun starts blank.

    Keyed widgets keep their value across st.rerun(); dropping the keys is how
    Streamlit resets them. Without this, the form still reads as filled in and
    a second click creates a duplicate topic — topic.name has no unique
    constraint, so nothing downstream catches it and students see both.
    """
    for key in NEW_TOPIC_KEYS:
        state.pop(key, None)


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

    usage_tab, content_tab, export_tab = st.tabs(
        ["Usage", "Content", "Export"], key="_hub.admin_tabs"
    )

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
    left.metric(analytics.identity_label(), summary["unique_visitors"])
    middle.metric("Sessions", summary["sessions"])
    right.metric("Experiment opens", summary["experiment_opens"])

    st.caption(
        f'"{analytics.identity_label()}" reflects what this deployment can actually '
        "measure — see docs/deployment-notes.md."
    )

    st.subheader("Which experiments students actually use")
    ranking = queries.experiment_ranking(engine, days)
    if not ranking:
        st.info("No experiment opens recorded in this period yet.")
        return
    st.dataframe(
        ranking, width="stretch", hide_index=True,
        key="_hub.usage_ranking",
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
        with st.expander(
            f"{topic['name']} — {topic['subtitle']}", expanded=False,
            key=f"_hub.texp_{topic['id']}",
        ):
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
            # delete_topic permanently drops this topic's name, subtitle and
            # unlock message and disables every experiment in it. There is no
            # undo, so it takes a deliberate second action rather than one
            # stray click next to Save.
            confirmed = delete.checkbox(
                "I understand this disables its experiments",
                key=f"_hub.tdelconfirm_{topic['id']}",
            )
            if delete.button(
                "⚠️ Delete topic (unassigns its experiments)",
                key=f"_hub.tdel_{topic['id']}",
                disabled=not confirmed,
            ):
                if not confirmed:
                    st.warning("Tick the confirmation box first.")
                else:
                    db.delete_topic(engine, topic["id"])
                    st.rerun()

    with st.expander("Add a new topic", key="_hub.newtopic_exp"):
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
            # topic.name has no unique constraint, and a keyed text_input keeps
            # its value across the rerun, so leaving these set means a second
            # click silently creates a duplicate topic that students see.
            clear_new_topic_form(st.session_state)
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
        with st.expander(
            f"{row['title']} · {exp_id}{flag}", expanded=False,
            key=f"_hub.eexp_{exp_id}",
        ):
            if row["orphaned"]:
                st.warning(
                    "This experiment no longer has a module in experiments/. It "
                    "is hidden from students but kept so its settings are not lost."
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
