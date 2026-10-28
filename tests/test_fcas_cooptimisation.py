"""The Topic 9 reference numbers, as tests.

Every number here was checked against HiGHS through scipy. The solver functions
are tested directly (no Streamlit), then the source guards, then the page.
"""
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from experiments import fcas_cooptimisation as fc
from experiments._kit import ed

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "fcas_cooptimisation.py"
A = pytest.approx


def approx(x):
    return pytest.approx(x, abs=1e-6)


# --- Mode 1: co-optimisation ------------------------------------------------

def test_forum_r80() -> None:
    s = fc.cooptimise("forum", 80)
    assert list(s["P"]) == approx([500, 300, 0])
    assert list(s["r"]) == approx([0, 80, 0])
    assert s["lam"] == approx(40) and s["pi"] == approx(4)
    assert fc.unique(s["lam_range"]) and fc.unique(s["pi_range"])
    assert s["pi_range"][0] == approx(4)


def test_forum_r150() -> None:
    s = fc.cooptimise("forum", 150)
    assert list(s["P"]) == approx([500, 250, 50])
    assert list(s["r"]) == approx([0, 150, 0])
    assert s["lam"] == approx(60) and s["pi"] == approx(24)
    assert fc.unique(s["lam_range"]) and fc.unique(s["pi_range"])
    assert s["cost"] == approx(23_600)
    assert s["reserve_cost"] == approx([41, 24, 30])


def test_forum_energy_first_r150() -> None:
    e = fc.energy_first("forum", 150)
    assert e["feasible"]
    assert e["cost"] == approx(23_900)
    assert e["lam"] == approx(40) and e["pi"] == approx(30)
    assert list(e["r"]) == approx([0, 100, 50])


def test_forum_reserve_first_r150() -> None:
    r = fc.reserve_first("forum", 150)
    assert r["feasible"]
    assert r["cost"] == approx(25_300)
    assert r["pi"] == approx(4) and r["lam"] == approx(60)
    assert list(r["P"]) == approx([400, 350, 50])


def test_forum_sweep_steps() -> None:
    pts = fc.sweep("forum")
    assert pts[-1][0] == 400  # infeasible above 400
    by = {int(R): (pi, lam) for R, pi, lam in pts}
    for R, pi in ((50, 4), (150, 24), (250, 30), (350, 41)):
        assert by[R][0] == approx(pi)
    assert by[50][1] == approx(40) and by[99][1] == approx(40)
    assert by[101][1] == approx(60) and by[350][1] == approx(60)
    assert fc.cooptimise("forum", 410) is None


def test_price_steps_are_clean_segments() -> None:
    got = fc.price_steps("forum", 0)
    want = [(0, 100, 4, 40), (100, 200, 24, 60), (200, 300, 30, 60), (300, 400, 41, 60)]
    assert len(got) == len(want)
    for g, w in zip(got, want):
        assert list(g) == approx(list(w))


def test_forum_r100_price_is_not_unique() -> None:
    s = fc.cooptimise("forum", 100)
    assert s["pi_range"] == approx((4, 24))
    assert s["lam_range"] == approx((40, 60))
    assert not fc.unique(s["pi_range"])


@pytest.mark.parametrize("R,left,right", [(0, 0, 4), (200, 24, 30), (300, 30, 41)])
def test_forum_other_breakpoints(R, left, right) -> None:
    rng = fc.cooptimise("forum", R)["pi_range"]
    assert rng == approx((left, right))
    assert not fc.unique(rng)


def test_forum_r400_has_no_right_hand_value() -> None:
    s = fc.cooptimise("forum", 400)
    assert s["pi_range"][0] == approx(41) and s["pi_range"][1] is None
    assert s["lam_range"][1] is None
    head, sentence = fc.fmt_price(s["pi_range"], fc._beyond_pi(400))
    assert head == "41 or more"
    assert "no feasible dispatch above 400 MW" in sentence


@pytest.mark.parametrize("batt,lam,pi", [(100, 40, 4), (200, 40, 1)])
def test_forum_battery(batt, lam, pi) -> None:
    s = fc.cooptimise("forum", 150, batt)
    assert s["lam"] == approx(lam) and s["pi"] == approx(pi)
    assert fc.unique(s["lam_range"]) and fc.unique(s["pi_range"])


@pytest.mark.parametrize("R,pi,lam,cost", [(100, 2, 40, 96_700), (300, 12, 50, 98_600),
                                           (500, 15, 50, 101_150), (1000, 31, 50, 109_450)])
def test_lecture_coopt(R, pi, lam, cost) -> None:
    s = fc.cooptimise("lecture", R)
    assert s["pi"] == approx(pi) and s["lam"] == approx(lam) and s["cost"] == approx(cost)
    assert fc.unique(s["pi_range"]) and fc.unique(s["lam_range"])


def test_lecture_infeasible_above_1100() -> None:
    assert fc.cooptimise("lecture", 1100) is not None
    assert fc.cooptimise("lecture", 1110) is None
    assert fc.cooptimise("lecture", 1100)["pi_range"][1] is None


def test_lecture_r300_full_costs_and_methods() -> None:
    s = fc.cooptimise("lecture", 300)
    assert s["reserve_cost"] == approx([12, 31, 15])
    assert fc.energy_first("lecture", 300)["cost"] == approx(99_050)
    assert fc.reserve_first("lecture", 300)["cost"] == approx(101_450)


def test_sequential_methods_never_beat_coopt() -> None:
    for preset, R in (("forum", 150), ("forum", 200), ("lecture", 300), ("lecture", 600)):
        c = fc.cooptimise(preset, R)["cost"]
        assert fc.reserve_first(preset, R)["cost"] >= c - 1e-6
        e = fc.energy_first(preset, R)
        assert e["cost"] >= c - 1e-6


def test_energy_first_headroom_and_failure() -> None:
    assert fc.ef_headroom("forum") == approx(200)
    assert fc.ef_headroom("lecture") == approx(650)
    assert fc.ef_headroom("forum", 50) == approx(250)
    assert fc.energy_first("forum", 210)["feasible"] is False
    assert fc.energy_first("forum", 200)["feasible"] is True
    assert fc.energy_first("lecture", 450)["feasible"] is True


def test_sequential_price_ranges() -> None:
    assert fc.energy_step_lam_range("forum") == approx((40, 40))
    assert fc.energy_first("forum", 100)["pi_range"] == approx((4, 30))
    assert fc.energy_first("forum", 200)["pi_range"][0] == approx(30)
    rf = fc.reserve_first_ranges("forum", 100)
    assert rf["pi_range"] == approx((1, 4))
    assert rf["lam_range"] == approx((40, 60))
    assert fc.reserve_first_ranges("forum", 150)["pi_range"] == approx((4, 4))


# --- Who sets the price -----------------------------------------------------

def test_setter_sentences() -> None:
    s = fc.cooptimise("forum", 150)
    assert fc.lam_setter("forum", s, 0) == "set by C's energy offer"
    assert "4 + (60 − 40) = 24" in fc.pi_setter("forum", s, 0)
    s = fc.cooptimise("forum", 80)
    assert fc.lam_setter("forum", s, 0) == "set by B's energy offer"
    assert fc.pi_setter("forum", s, 0) == "set by B's reserve offer: B has spare headroom"
    s = fc.cooptimise("forum", 150, 200)
    assert fc.pi_setter("forum", s, 200) == "set by the battery's offer"


def test_verdicts_follow_quantities() -> None:
    s = fc.cooptimise("forum", 150)
    v = {row[0]: row[4] for row in fc.verdicts("forum", s, 0, True)}
    assert v["B"] == "holds reserve; its full cost equals the price"
    assert v["A"] == "holds none: its full cost is above the price"
    # A breakpoint: no 'above the price' clause when the price is not unique.
    s = fc.cooptimise("forum", 300)
    v = {row[0]: row[4] for row in fc.verdicts("forum", s, 0, False)}
    assert all("above the price" not in x for x in v.values())
    s = fc.cooptimise("forum", 150, 100)
    assert fc.verdicts("forum", s, 100, True)[-1][4] == "holds all it offers"


def test_settlement_adds_up() -> None:
    s = fc.cooptimise("forum", 150)
    st = fc.settlement("forum", s, 150)
    assert st["consumers"] == approx(60 * 800)
    assert st["bill"] == approx(24 * 150)
    assert [r["total"] for r in st["rows"]] == approx([40 * 500, 20 * 250 + 20 * 150, 0])
    assert len(st["checks"]) == 1 and st["checks"][0]["name"] == "B"
    assert st["checks"][0]["e_margin"] == approx(st["checks"][0]["r_margin"])


# --- Lower, global and local ------------------------------------------------

def test_lower_forum_midday() -> None:
    s = fc.lower_lp("forum_midday", 30)
    assert list(s["P"]) == approx([770, 230])
    assert s["lam"] == approx(25) and s["pi"] == approx(47)
    rng = fc.lower_ranges("forum_midday", 30)
    assert fc.unique(rng["pi_range"]) and fc.unique(rng["lam_range"])
    assert fc.lower_setter("forum_midday", s)["name"] == "Gas"


def test_lower_lecture_midday() -> None:
    s = fc.lower_lp("lecture_midday", 50)
    assert list(s["P"]) == approx([650, 850])
    assert s["lam"] == approx(20) and s["pi"] == approx(21)
    assert fc.unique(fc.lower_ranges("lecture_midday", 50)["pi_range"])


def test_global_local_80() -> None:
    s = fc.global_local(80)
    assert list(s["x"]) == approx([320, 40, 40])
    assert s["piG"] == approx(3) and s["piSA"] == approx(47)
    assert s["price_SA"] == approx(50)
    r = fc.gl_ranges(80)
    assert fc.unique(r["piSA_range"]) and fc.unique(r["sa_range"])


def test_global_local_30_and_40() -> None:
    s = fc.global_local(30)
    assert s["piSA"] == approx(7) and s["price_SA"] == approx(10)
    r = fc.gl_ranges(40)
    assert r["piSA_range"] == approx((7, 47))
    assert r["sa_range"] == approx((10, 50))


# --- Trapeziums -------------------------------------------------------------

def avail(preset, service, P, gr=0.0, gl=0.0):
    t = fc.TRAP_PRESETS[preset]["services"][service]
    return fc.availability(t, P, gr, gl, service)


def test_forum_fast_raise() -> None:
    t = fc.TRAP_PRESETS["forum"]["services"]["Fast raise"]
    assert fc.slopes(t) == approx((1.25, 0.75))
    assert [avail("forum", "Fast raise", p)[0] for p in (90, 130, 250, 350)] == approx([0, 40, 80, 40])
    assert avail("forum", "Fast raise", 350, gr=15) == (approx(28), "right row")
    assert avail("forum", "Fast raise", 250)[1] == "flat top"
    assert avail("forum", "Fast raise", 130)[1] == "left row"
    assert avail("forum", "Fast raise", 90)[1] == "outside enablement range"


def test_lecture_fast_raise() -> None:
    got = [avail("lecture", "Fast raise", p)[0] for p in (180, 225, 350, 480)]
    assert got == approx([0, 50, 100, 40])
    assert avail("lecture", "Fast raise", 480, gr=20)[0] == approx(0)
    assert avail("lecture", "Fast raise", 470, gr=10)[0] == approx(40)


def test_battery_fast_raise_and_lower() -> None:
    assert [avail("battery", "Fast raise", p)[0] for p in (-60, 0, 60, 100)] == approx([100, 100, 40, 0])
    assert [avail("battery", "Fast lower", p)[0] for p in (-60, 0, 60)] == approx([40, 100, 100])


def test_regulation_does_not_reduce_itself() -> None:
    a = avail("forum", "Regulation raise", 350, gr=30)[0]
    assert a == avail("forum", "Regulation raise", 350)[0]
    assert fc.effective_g("Regulation raise", 30, 10) == (0.0, 0.0)
    assert fc.effective_g("Fast lower", 30, 10) == (0.0, 10)


def test_reg_cap() -> None:
    assert fc.reg_cap("lecture", 480, "raise") == approx(20)
    assert fc.reg_cap("lecture", 480, "lower") == 0.0
    assert fc.reg_cap("forum", 350, "raise") == approx(40)


def test_trap_steps_text() -> None:
    t = fc.TRAP_PRESETS["forum"]["services"]["Fast raise"]
    steps = {s["row"]: s for s in fc.trap_steps(t, 350, 15, 0, "Fast raise")}
    assert "(400 - 350 - 15) / 1.25 = 28" in steps["right row"]["tex"]
    assert "(350 - 100) / 0.75 = 333.3" in steps["left row"]["tex"]
    reg = fc.TRAP_PRESETS["lecture"]["services"]["Regulation raise"]
    steps = {s["row"]: s for s in fc.trap_steps(reg, 400, 0, 0, "Regulation raise")}
    assert steps["left row"]["value"] is None  # vertical side
    assert steps["right row"]["value"] == approx(100)


# --- Source guards ----------------------------------------------------------

BANNED = ("—", "4087", "7087", "The University of Adelaide")
ALLOWED_COLOURS = {ed.NAVY, ed.PURPLE, ed.LAVENDER, ed.SILVER, ed.LIMESTONE,
                   ed.MUTED, "#FFFFFF"}


def test_no_banned_strings() -> None:
    text = SOURCE.read_text()
    for banned in BANNED:
        assert banned not in text, f"fcas_cooptimisation.py contains {banned!r}"


def test_only_palette_colours() -> None:
    found = set(re.findall(r"#[0-9A-Fa-f]{6}", SOURCE.read_text()))
    assert found <= ALLOWED_COLOURS, found - ALLOWED_COLOURS


def test_every_key_has_the_fc_prefix() -> None:
    text = SOURCE.read_text()
    keys = re.findall(r"""key=f?["']([^"']*)["']""", text)
    keys += re.findall(r"""_kept\(\s*f?["']([^"']*)["']""", text)
    keys += re.findall(r"""_put\(\s*f?["']([^"']*)["']""", text)
    assert keys
    assert all(k.startswith("fc_") for k in keys), keys
    assert "set_page_config" not in text
    assert "use_container_width" not in text
    assert "STATE_GROUP" not in text


def test_defaults_are_all_fc_keys() -> None:
    assert all(k.startswith("fc_") for k in fc.DEFAULTS)


def test_pure_section_has_no_streamlit_calls() -> None:
    pure = SOURCE.read_text().split("# Charts")[0]
    body = pure.split("from experiments._kit import ed")[1].split("# Cached wrappers")[0]
    assert not re.search(r"(?<![\w.])st\.", body)


# --- Page -------------------------------------------------------------------

HARNESS = (
    "import sys\n"
    f"sys.path.insert(0, {str(ROOT)!r})\n"
    "from experiments import fcas_cooptimisation\n"
    "fcas_cooptimisation.render()\n"
)


def fresh() -> AppTest:
    return AppTest.from_string(HARNESS, default_timeout=240).run()


def clean(app) -> None:
    assert not app.exception, "; ".join(e.message for e in app.exception)


def radio(app, key):
    return next(r for r in app.radio if r.key == key)


def texts(app) -> str:
    return "\n".join([m.value for m in app.markdown] + [m.value for m in app.metric]
                     + [m.value for m in app.caption] + [m.value for m in app.latex])


def go_mode(app, i):
    radio(app, "fc_mode").set_value(fc.MODES[i]).run()
    clean(app)


def test_every_mode_and_preset_renders() -> None:
    app = fresh()
    clean(app)
    for preset in fc.RAISE_PRESETS:
        radio(app, "fc_raise_preset").set_value(preset).run()
        clean(app)
        for m in fc.METHODS:
            app.checkbox(key=f"fc_show_{m}").uncheck().run()
            clean(app)
            app.checkbox(key=f"fc_show_{m}").check().run()
            clean(app)
    go_mode(app, 1)
    for unit in fc.TRAP_PRESETS:
        radio(app, "fc_trap_unit").set_value(unit).run()
        clean(app)
        for service in fc.TRAP_PRESETS[unit]["services"]:
            radio(app, "fc_service").set_value(service).run()
            clean(app)
    go_mode(app, 2)
    for preset in fc.LOWER_PRESETS:
        radio(app, "fc_lower_preset").set_value(preset).run()
        clean(app)
    go_mode(app, 3)
    clean(app)


@pytest.mark.parametrize("batt", [0, 100, 200])
def test_mode_one_batteries(batt) -> None:
    app = fresh()
    app.slider(key="fc_batt").set_value(batt).run()
    clean(app)
    body = texts(app)
    for name in fc.METHOD_SHORT.values():
        assert name in body


def test_mode_one_default_numbers() -> None:
    app = fresh()
    assert [m.value for m in app.metric] == ["60", "24"]
    assert "4 + (60 − 40) = 24" in texts(app)


def test_mode_one_breakpoint_and_end_of_range() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(100).run()
    clean(app)
    assert [m.value for m in app.metric] == ["between 40 and 60", "between 4 and 24"]
    assert "not unique" in texts(app)
    app.slider(key="fc_R").set_value(400).run()
    clean(app)
    assert "no feasible dispatch above 400 MW" in texts(app)


def test_mode_one_energy_first_failure_words() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(250).run()
    clean(app)
    assert "cannot find 250 MW of raise in the headroom left after the energy market" in texts(app)
    assert "Not drawn, because it cannot meet the requirement: energy first." in texts(app)
    assert "only 200 MW is left" in texts(app)


def test_preset_change_resets_the_knobs() -> None:
    app = fresh()
    app.slider(key="fc_batt").set_value(100).run()
    radio(app, "fc_raise_preset").set_value("lecture").run()
    clean(app)
    assert app.slider(key="fc_R").value == 300
    assert app.slider(key="fc_batt").value == 0
    radio(app, "fc_raise_preset").set_value("forum").run()
    assert app.slider(key="fc_R").value == 150


def test_state_survives_a_mode_round_trip() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(200).run()
    app.checkbox(key="fc_show_rf").uncheck().run()
    n = len(app.session_state["fc_trail_raise"])
    go_mode(app, 1)
    go_mode(app, 0)
    assert app.slider(key="fc_R").value == 200
    assert app.checkbox(key="fc_show_rf").value is False
    assert len(app.session_state["fc_trail_raise"]) == n


def test_mode_two_regulation_moves_the_right_row() -> None:
    app = fresh()
    go_mode(app, 1)
    app.slider(key="fc_g_raise").set_value(15).run()
    clean(app)
    body = texts(app)
    assert "= 28" in body and "Available: 28 MW" in body


def test_mode_two_clamp_line_and_outside_range() -> None:
    app = fresh()
    go_mode(app, 1)
    radio(app, "fc_trap_unit").set_value("lecture").run()
    app.slider(key="fc_P").set_value(480).run()
    app.slider(key="fc_g_raise").set_value(25).run()
    clean(app)
    assert "limited to 20 MW by its own trapezium" in texts(app)
    app.slider(key="fc_P").set_value(150).run()
    clean(app)
    assert "outside" in texts(app) and "0 MW" in texts(app)


def test_mode_two_battery_numbers() -> None:
    app = fresh()
    go_mode(app, 1)
    radio(app, "fc_trap_unit").set_value("battery").run()
    clean(app)
    assert app.slider(key="fc_P").value == -60
    assert "Available: 100 MW" in texts(app)
    app.slider(key="fc_P").set_value(60).run()
    assert "Available: 40 MW" in texts(app)


def test_mode_three_and_four_numbers() -> None:
    app = fresh()
    go_mode(app, 2)
    assert [m.value for m in app.metric] == ["25", "47"]
    go_mode(app, 3)
    assert [m.value for m in app.metric] == ["3", "47"]
    app.slider(key="fc_RSA").set_value(40).run()
    clean(app)
    assert "between 7 and 47" in [m.value for m in app.metric]


def table(app, start: str) -> str:
    """The markdown table that begins with `start`."""
    return next(m.value for m in app.markdown if m.value.startswith(start))


def test_method_table_shows_ranges_at_a_breakpoint() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(100).run()
    clean(app)
    body = table(app, "| Method")
    assert "between 40 and 60" in body and "between 4 and 24" in body
    assert "between 1 and 4" in body  # reserve first


# --- The trail and the method comparison ---------------------------------------

def test_trail_push_dedupes_and_caps() -> None:
    def e(k):
        return dict(knobs=(k,))
    t = fc.trail_push([], e(150))
    assert len(fc.trail_push(t, e(150))) == 1
    t = fc.trail_push(fc.trail_push(t, e(200)), e(150))
    assert [x["n"] for x in t] == [1, 2, 3]
    before = []
    for k in range(14):
        new = fc.trail_push(before, e(k))
        assert new is not before
        before = new
    assert len(before) == 12 and [x["n"] for x in before] == list(range(3, 15))
    snap = list(before)
    fc.trail_push(before, e(99))
    assert before == snap


def test_trail_marks_merges_coincident_points() -> None:
    got = fc.trail_marks([(2, 150, 24, "a", False), (3, 100, 4, "b", True),
                          (5, 150.0000001, 24, "c", False)])
    assert len(got) == 2
    assert got[0][2] == "2, 5" and got[0][3] == "a<br>c"
    assert got[1][2] == "3" and got[1][4] is True


def test_method_costs_forum_150() -> None:
    rows = {int(r[0]): r for r in fc.method_costs("forum", 0)}
    assert rows[150][1:] == approx((23_600, 23_900, 25_300))
    assert rows[250][2] is None


def trail(app, name="raise"):
    return app.session_state[f"fc_trail_{name}"]


def test_three_methods_shown_at_150() -> None:
    app = fresh()
    assert not [r for r in app.radio if r.key == "fc_method"]
    body = texts(app)
    for cost in ("23 600", "23 900", "25 300"):
        assert cost in body
    assert all(app.checkbox(key=f"fc_show_{m}").value for m in fc.METHODS)


def test_unticking_a_method_hides_it() -> None:
    app = fresh()
    app.checkbox(key="fc_show_ef").uncheck().run()
    clean(app)
    body = table(app, "| Method")
    assert "23 900" not in body and "23 600" in body and "25 300" in body
    assert "23 900" not in table(app, "| Run")
    assert len(trail(app)) == 1
    app.checkbox(key="fc_show_coopt").uncheck().run()
    app.checkbox(key="fc_show_rf").uncheck().run()
    clean(app)
    assert "Tick at least one clearing method" in texts(app)
    app.checkbox(key="fc_show_ef").check().run()
    assert "23 900" in table(app, "| Method")


def spec_of(app, title: str) -> dict:
    for e in app.get("plotly_chart"):
        if title in e.proto.spec:
            return json.loads(e.proto.spec)
    raise AssertionError(title)


def earlier(spec: dict, name: str, yaxis: str = "y") -> dict:
    return next(t for t in spec["data"] if t.get("name") == name
                and (t.get("yaxis") or "y") == yaxis)


def test_supply_curve_earlier_runs() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(50).run()
    app.slider(key="fc_batt").set_value(100).run()
    app.slider(key="fc_R").set_value(150).run()
    app.slider(key="fc_batt").set_value(0).run()
    clean(app)
    assert [e["n"] for e in trail(app)] == [1, 2, 3, 4, 5]
    spec = spec_of(app, "The reserve supply curve")
    circles = earlier(spec, "earlier runs (number = run)")
    assert circles["x"] == [150, 50] and circles["y"] == [24, 4]
    assert circles["text"] == ["1", "2"] and circles["marker"]["symbol"] == "circle"
    squares = earlier(spec, "earlier runs, other battery value")
    assert squares["x"] == [50, 150] and squares["y"] == [1, 4]
    assert squares["text"] == ["3", "4"] and squares["marker"]["symbol"] == "square"
    lam = earlier(spec, "earlier runs (number = run)", "y2")
    assert lam["y"] == [60, 40]


def test_trail_records_slider_changes() -> None:
    app = fresh()
    assert len(trail(app)) == 1
    app.slider(key="fc_R").set_value(100).run()
    app.slider(key="fc_R").set_value(200).run()
    clean(app)
    assert [e["R"] for e in trail(app)] == [150, 100, 200]
    assert [e["n"] for e in trail(app)] == [1, 2, 3]
    app.run()
    assert len(trail(app)) == 3
    app.slider(key="fc_batt").set_value(100).run()
    assert len(trail(app)) == 4


def test_trail_resets_on_preset_change() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(100).run()
    app.slider(key="fc_R").set_value(200).run()
    radio(app, "fc_raise_preset").set_value("lecture").run()
    clean(app)
    assert [(e["R"], e["n"]) for e in trail(app)] == [(300, 1)]
    radio(app, "fc_raise_preset").set_value("forum").run()
    assert [(e["R"], e["n"]) for e in trail(app)] == [(150, 1)]


def test_clear_history() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(100).run()
    app.slider(key="fc_R").set_value(200).run()
    app.button(key="fc_clear_raise").click().run()
    clean(app)
    assert len(trail(app)) == 1 and trail(app)[0]["n"] == 1 and trail(app)[0]["R"] == 200


def test_mode_two_trail() -> None:
    app = fresh()
    go_mode(app, 1)
    app.slider(key="fc_P").set_value(250).run()
    app.slider(key="fc_P").set_value(130).run()
    clean(app)
    assert len(trail(app, "trap")) == 3
    radio(app, "fc_service").set_value("Slow raise").run()
    clean(app)
    assert len(trail(app, "trap")) == 4
    radio(app, "fc_trap_unit").set_value("battery").run()
    clean(app)
    t = trail(app, "trap")
    assert len(t) == 1 and t[0]["P"] == -60


def test_mode_three_and_four_trails() -> None:
    app = fresh()
    go_mode(app, 2)
    app.slider(key="fc_Rm").set_value(40).run()
    clean(app)
    assert len(trail(app, "lower")) == 2
    go_mode(app, 3)
    app.slider(key="fc_RSA").set_value(40).run()
    app.slider(key="fc_RSA").set_value(30).run()
    clean(app)
    assert len(trail(app, "gl")) == 3
    assert "between 10 and 50" in table(app, "| Run")
    app.button(key="fc_clear_gl").click().run()
    clean(app)
    assert len(trail(app, "gl")) == 1


def test_clear_history_in_modes_two_and_three() -> None:
    app = fresh()
    go_mode(app, 1)
    app.slider(key="fc_P").set_value(250).run()
    app.slider(key="fc_P").set_value(130).run()
    app.button(key="fc_clear_trap").click().run()
    clean(app)
    assert len(trail(app, "trap")) == 1 and trail(app, "trap")[0]["P"] == 130
    go_mode(app, 2)
    app.slider(key="fc_Rm").set_value(40).run()
    app.button(key="fc_clear_lower").click().run()
    clean(app)
    assert len(trail(app, "lower")) == 1 and trail(app, "lower")[0]["Rm"] == 40


def test_mode_two_other_regulation_follows_the_service() -> None:
    app = fresh()
    go_mode(app, 1)
    radio(app, "fc_service").set_value("Fast lower").run()
    app.slider(key="fc_g_raise").set_value(15).run()  # Fast lower does not see it
    app.slider(key="fc_P").set_value(300).run()
    clean(app)
    spec = spec_of(app, "Fast lower: the trapezium")
    assert not [t for t in spec["data"] if t.get("name") == "earlier runs, other regulation"]
    circles = earlier(spec, "earlier runs (number = run)")
    assert circles["text"] == ["2, 3"]
    app.slider(key="fc_g_lower").set_value(15).run()  # now it does
    spec = spec_of(app, "Fast lower: the trapezium")
    squares = earlier(spec, "earlier runs, other regulation")
    assert squares["marker"]["symbol"] == "square" and squares["text"] == ["2, 3", "4"]
