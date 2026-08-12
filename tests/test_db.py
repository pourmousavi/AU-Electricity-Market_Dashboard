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


def test_seed_parks_every_experiment_in_one_disabled_topic(engine) -> None:
    """An experiment module carries no opinion about where it belongs.

    The topic layout is the coordinator's, made in the admin panel, so the
    seed only guarantees nothing is invisible there -- and nothing reaches a
    student until it is placed deliberately.
    """
    cat = load_catalogue()
    assert db.seed_initial(engine, cat) is True

    topics = db.list_topics(engine, include_disabled=True)
    assert [t["name"] for t in topics] == ["Unsorted"]
    assert topics[0]["enabled"] is False

    rows = db.list_experiments(engine, topic_id=None, include_disabled=True)
    assert len(rows) == 25
    assert not any(r["enabled"] for r in rows)
    assert all(r["topic_id"] == topics[0]["id"] for r in rows)


def test_seeded_experiments_are_invisible_to_students(engine) -> None:
    db.seed_initial(engine, load_catalogue())
    assert db.list_experiments(engine, topic_id=None, include_disabled=False) == []


def test_seed_is_idempotent(engine) -> None:
    cat = load_catalogue()
    assert db.seed_initial(engine, cat) is True
    assert db.seed_initial(engine, cat) is False
    assert len(db.list_topics(engine, include_disabled=True)) == 1


def test_reconcile_inserts_new_ids_disabled_and_unassigned(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)

    from hub.catalogue import Experiment

    extra = dict(cat)
    extra["brand_new"] = Experiment(
        id="brand_new", path=cat["consumer_model"].path.parent / "brand_new.py",
    )
    inserted, orphaned = db.reconcile(engine, extra)
    assert inserted == 1 and orphaned == 0

    row = db.get_experiment(engine, "brand_new")
    assert row["enabled"] is False
    assert row["topic_id"] is None


def test_reconcile_marks_missing_ids_orphaned_without_deleting(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)

    shrunk = {k: v for k, v in cat.items() if k != "power_flow_theory"}
    inserted, orphaned = db.reconcile(engine, shrunk)
    assert inserted == 0 and orphaned == 1

    row = db.get_experiment(engine, "power_flow_theory")
    assert row is not None and row["orphaned"] is True


def test_orphaned_experiments_are_hidden_from_students(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)
    db.reconcile(engine, {k: v for k, v in cat.items() if k != "power_flow_theory"})

    visible = db.list_experiments(engine, topic_id=None, include_disabled=False)
    assert "power_flow_theory" not in {r["experiment_id"] for r in visible}


def test_toggle_and_reassign(engine) -> None:
    cat = load_catalogue()
    db.seed_initial(engine, cat)
    unsorted_id = db.list_topics(engine, include_disabled=True)[0]["id"]

    db.set_experiment_enabled(engine, "power_flow_theory", False)
    assert db.get_experiment(engine, "power_flow_theory")["enabled"] is False

    db.assign_experiment(engine, "power_flow_theory", topic_id=unsorted_id, sort_order=99)
    row = db.get_experiment(engine, "power_flow_theory")
    assert row["topic_id"] == unsorted_id and row["sort_order"] == 99


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
    db.update_experiment_text(engine, "consumer_model", "Demand Curves", "Start here.")
    row = db.get_experiment(engine, "consumer_model")
    assert row["title"] == "Demand Curves"
    assert row["blurb"] == "Start here."


def test_seed_does_not_rerun_when_topics_deleted_but_experiments_remain(engine) -> None:
    """delete_topic deliberately keeps experiments (unassigned, disabled).

    That leaves the topic table empty with the experiment table still
    populated -- reachable purely through the shipped admin API (delete
    every topic). seed_initial must not mistake that for a genuine
    first-boot empty database and try to re-insert existing experiment ids.
    """
    cat = load_catalogue()
    db.seed_initial(engine, cat)

    for t in db.list_topics(engine, include_disabled=True):
        db.delete_topic(engine, t["id"])

    assert db.list_topics(engine, include_disabled=True) == []
    assert len(db.list_experiments(engine, topic_id=None, include_disabled=True)) == 25

    assert db.seed_initial(engine, cat) is False
