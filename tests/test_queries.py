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
        # Every dict needs the same key set: SQLAlchemy 2.0 compiles a
        # multi-row insert() from the first row's keys, and later rows
        # missing one of those keys raise InvalidRequestError.
        base = {"experiment_id": None, "dwell_ms": None, "ts": now}
        conn.execute(insert(db.event), [
            base | {"session_id": "s1", "kind": "experiment_open",
                    "experiment_id": "w2.consumer_model"},
            base | {"session_id": "s2", "kind": "experiment_open",
                    "experiment_id": "w2.consumer_model"},
            base | {"session_id": "s3", "kind": "experiment_open",
                    "experiment_id": "w7.pareto"},
            base | {"session_id": "s1", "kind": "experiment_close",
                    "experiment_id": "w2.consumer_model", "dwell_ms": 10_000},
            base | {"session_id": "s2", "kind": "experiment_close",
                    "experiment_id": "w2.consumer_model", "dwell_ms": 30_000},
            base | {"session_id": "s1", "kind": "home_view"},
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
