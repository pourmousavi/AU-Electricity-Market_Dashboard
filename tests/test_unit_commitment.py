"""The Topic 8 reference numbers, as tests.

Every number here was checked against HiGHS through scipy (milp with
mip_rel_gap = 0, then linprog for the pricing run). Several optima are
degenerate: equal-cost schedules exist, so the tests that touch them assert
ranges, sums or robust facts rather than one vertex.
"""
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from experiments import unit_commitment as uc
from experiments._kit import ed

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "unit_commitment.py"
U = ("G1", "G2", "G3", "G4")


def dollars(value):
    return pytest.approx(value, abs=0.1)


def sched(res, k):
    return res["sched"][k]


# (stage, total, energy, no-load, start-up, G3, G4); None means not asserted.
STAGE_TABLE = [
    (1, 572_000, 496_000, 61_000, 15_000, "00000110", "00000000"),
    (2, 575_000, 515_000, 57_000, 3_000, "00000000", "00000110"),
    (3, 536_307.5, 480_307.5, 56_000, 0, "00000000", "00000000"),
    (4, 613_121.1, 527_121.1, 68_000, 18_000, "00001111", "11110000"),
    (5, 615_821.1, 529_821.1, 68_000, 18_000, "00001111", "11110000"),
    (6, 644_280.5, None, None, None, "00001111", "11110010"),
]


@pytest.mark.parametrize("stage,total,energy,noload,startup,g3,g4", STAGE_TABLE)
def test_stage_totals_and_schedules(stage, total, energy, noload, startup, g3, g4) -> None:
    r = uc.solve_stage(stage)
    assert r["ok"]
    c = r["costs"]
    assert c["total"] == dollars(total)
    if energy is not None:
        assert c["energy"] == dollars(energy)
        assert c["noload"] == dollars(noload)
        assert c["startup"] == dollars(startup)
    assert c["total"] == dollars(c["energy"] + c["noload"] + c["startup"])
    assert sched(r, "G3") == g3
    assert sched(r, "G4") == g4
    assert sched(r, "G1") == sched(r, "G2") == "1" * 8


def test_hour_by_hour() -> None:
    h = uc.hour_by_hour_result()
    assert h["costs"]["total"] == dollars(575_000)
    assert sched(h, "G3") == "00000000"
    assert sched(h, "G4") == "00000110"
    assert sched(h, "G1") == sched(h, "G2") == "1" * 8
    # Its cost split equals the look-ahead stage 2 schedule.
    assert h["costs"]["energy"] == dollars(515_000)
    assert h["costs"]["noload"] == dollars(57_000)
    assert h["costs"]["startup"] == dollars(3_000)
    assert h["costs"]["total"] - uc.solve_stage(1)["costs"]["total"] == dollars(3_000)


@pytest.mark.parametrize("ut,total", [(1, 572_000), (2, 572_000), (3, 575_000), (4, 575_000)])
def test_knob_two_moves_stage_two(ut, total) -> None:
    r = uc.solve_stage(2, ut)
    assert r["costs"]["total"] == dollars(total)
    assert sched(r, "G1") == sched(r, "G2") == "1" * 8


@pytest.mark.parametrize("stage,total", [(3, 536_307.5), (4, 613_121.1), (5, 615_821.1)])
def test_knob_two_leaves_later_stages(stage, total) -> None:
    for ut in (1, 2, 4):
        assert uc.solve_stage(stage, ut)["costs"]["total"] == dollars(total)


def test_stage_one_ignores_the_knob() -> None:
    assert uc.solve_stage(1, 1)["costs"]["total"] == dollars(572_000)
    assert uc.solve_stage(1, 4)["sched"] == uc.solve_stage(1, 3)["sched"]


# --- Trip check -------------------------------------------------------------

def contrib(t, name):
    return next(row["contribution"] for row in t["rows"] if row["name"] == name)


def test_trip_stage_three_hour_seven_fails() -> None:
    v = uc.solve_stage(3)["view"]
    assert v["P"]["G1"][6] == dollars(1500) and v["P"]["G2"][6] == dollars(1000)
    assert v["Pd"][6] - v["Pc"][6] == dollars(300)
    t = uc.trip(v, 3, 7, "G1")
    assert t["lost"] == dollars(1500)
    assert t["available"] == dollars(100)
    assert contrib(t, "BESS") == dollars(100)
    assert not t["ok"]


def test_trip_stage_four_hour_seven_passes_exactly() -> None:
    v = uc.solve_stage(4)["view"]
    assert [v["P"][k][6] for k in U] == pytest.approx([950, 950, 900, 0], abs=0.1)
    assert v["Pd"][6] - v["Pc"][6] == pytest.approx(0, abs=0.1)
    t = uc.trip(v, 4, 7, "G1")
    assert t["lost"] == dollars(950)
    assert contrib(t, "G2") == dollars(50)
    assert contrib(t, "G3") == dollars(500)
    assert contrib(t, "BESS") == dollars(400)
    assert t["available"] >= t["lost"] - 1e-6  # 950 against 950
    assert t["ok"]


def test_stage_four_g4_runs_at_minimum_in_hours_one_to_four() -> None:
    v = uc.solve_stage(4)["view"]
    assert v["P"]["G4"][:4] == pytest.approx([60] * 4, abs=0.1)


def test_trip_g2_with_and_without_g4() -> None:
    """Hour 1; hour 2 is degenerate so it is not pinned.

    The 1110 and 850 are solver-path dependent (HiGHS dual simplex vertex).
    """
    v = uc.solve_stage(4)["view"]
    t = uc.trip(v, 4, 1, "G2")
    assert t["lost"] == pytest.approx(v["P"]["G2"][0])
    assert t["available"] == pytest.approx(sum(row["contribution"] for row in t["rows"]))
    assert contrib(t, "G1") == dollars(450)
    assert contrib(t, "G4") == dollars(260)
    assert contrib(t, "BESS") == dollars(400)
    assert t["available"] == dollars(1110)
    assert t["ok"]
    t = uc.trip(v, 4, 1, "G2", include={"G4": False})
    assert t["available"] == dollars(850)
    assert t["lost"] == dollars(1000)
    assert not t["ok"]


def test_trip_edge_cases() -> None:
    v1 = uc.solve_stage(1)["view"]
    t = uc.trip(v1, 1, 7, "G1")
    assert all(row["name"] != "BESS" for row in t["rows"])  # no battery before stage 3
    off = uc.trip(v1, 1, 1, "G4")
    assert not off["committed"] and off["lost"] == 0


# --- Pricing run, settlement ------------------------------------------------

LAMBDA_A = {
    1: [20, 20, 20, 40, 40, 40, 40, 40],
    2: [20, 20, 20, 40, 40, 25, 25, 30],
    3: [20, 20, 20, 40, 40, 55, 55, 50],
}


def test_stage_five_prices_and_multiplier() -> None:
    p = uc.prices(5)
    assert p["ok"]
    for bus, lam in LAMBDA_A.items():
        assert p["lam"][bus] == pytest.approx(lam, abs=0.01)
    n1 = p["n1_g3"]
    assert n1[5] == pytest.approx(5, abs=0.01) and n1[6] == pytest.approx(5, abs=0.01)


def test_stage_five_flows_hour_seven() -> None:
    f = uc.solve_stage(5)["view"]["f"]
    assert f["1-2"][6] == pytest.approx(-75, abs=0.1)
    assert f["1-3"][6] == pytest.approx(725, abs=0.1)
    assert f["2-3"][6] == pytest.approx(800, abs=0.1)


def test_stage_five_settlement_with_degeneracy() -> None:
    s = uc.prices(5)["settlement"]
    g = s["gens"]
    assert g["G1"]["profit"] == dollars(-68_000)
    assert g["G2"]["profit"] == dollars(35_250)
    assert g["G4"]["profit"] == dollars(-25_400)
    assert -21_500 - 0.1 <= g["G3"]["profit"] <= -21_150 + 0.1
    assert 11_478.9 - 0.1 <= s["battery"] <= 11_828.9 + 0.1
    assert g["G3"]["profit"] + s["battery"] == dollars(-9_671.1)
    assert s["consumers"] == dollars(644_000)
    assert s["rent"] == dollars(96_000)
    assert 114_550 - 0.1 <= s["uplift"] <= 114_900 + 0.1
    assert g["G1"]["uplift"] == dollars(68_000)
    assert g["G2"]["uplift"] == 0
    assert 0.1860 <= s["share"] <= 0.1866


def test_case_b_is_infeasible_for_the_scuc_schedule() -> None:
    assert not uc.stage4_schedule_feasible_in_case_b()
    assert uc.max_hour7_demand_case_b() == pytest.approx(2725, abs=0.01)


def test_case_b_prices_run() -> None:
    p = uc.prices(6)
    assert p["ok"] and set(p["lam"]) == {1, 2, 3}


# --- Source guards ----------------------------------------------------------

BANNED = ("—", "4087", "7087", "The University of Adelaide", '"tight"',
          "is tight", "are tight")
ALLOWED_COLOURS = {ed.NAVY, ed.PURPLE, ed.LAVENDER, ed.SILVER, ed.LIMESTONE,
                   ed.MUTED, "#FFFFFF"}


def test_no_banned_strings() -> None:
    text = SOURCE.read_text()
    for banned in BANNED:
        assert banned not in text, f"unit_commitment.py contains {banned!r}"


def test_only_palette_colours() -> None:
    found = set(re.findall(r"#[0-9A-Fa-f]{6}", SOURCE.read_text()))
    assert found <= ALLOWED_COLOURS, found - ALLOWED_COLOURS


def test_every_key_has_the_uc_prefix() -> None:
    text = SOURCE.read_text()
    keys = re.findall(r"""key=f?["']([^"']*)["']""", text)
    assert keys
    assert all(k.startswith("uc_") for k in keys), keys
    assert "set_page_config" not in text
    assert "use_container_width" not in text
    assert "STATE_GROUP" not in text


def test_defaults_are_all_uc_keys() -> None:
    assert all(k.startswith("uc_") for k in uc.DEFAULTS)


# --- Page -------------------------------------------------------------------

HARNESS = (
    "import sys\n"
    f"sys.path.insert(0, {str(ROOT)!r})\n"
    "from experiments import unit_commitment\n"
    "unit_commitment.render()\n"
)


def fresh() -> AppTest:
    return AppTest.from_string(HARNESS, default_timeout=240).run()


def clean(app) -> None:
    assert not app.exception, "; ".join(e.message for e in app.exception)


def radio(app, key):
    return next(r for r in app.radio if r.key == key)


def test_page_renders_every_stage_and_panel() -> None:
    app = fresh()
    clean(app)
    for stage in range(1, 7):
        radio(app, "uc_stage").set_value(stage).run()
        clean(app)
        for panel in uc.PANELS:
            radio(app, "uc_panel").set_value(panel).run()
            clean(app)
            if panel == uc.PANELS[1]:  # trip check: a few hours and units
                for hour, unit in ((7, "G1"), (1, "G2"), (3, "G4")):
                    radio(app, "uc_trip_hour").set_value(hour)
                    radio(app, "uc_trip_unit").set_value(unit).run()
                    clean(app)
                app.checkbox(key="uc_trip_inc_G4").uncheck().run()
                clean(app)
                app.checkbox(key="uc_trip_inc_G4").check().run()
            if panel == uc.PANELS[2] and stage >= 5:
                radio(app, "uc_net_hour").set_value(6).run()
                clean(app)
                radio(app, "uc_net_hour").set_value(7).run()


def test_page_both_knobs() -> None:
    app = fresh()
    app.toggle(key="uc_hbh").set_value(True).run()
    clean(app)
    radio(app, "uc_stage").set_value(2).run()
    for ut in (1, 4):
        app.slider(key="uc_ut_g3").set_value(ut).run()
        clean(app)


def test_previous_and_next_buttons() -> None:
    app = fresh()
    app.button(key="uc_next").click().run()
    clean(app)
    assert app.session_state["uc_stage"] == 2
    app.button(key="uc_prev").click().run()
    assert app.session_state["uc_stage"] == 1
