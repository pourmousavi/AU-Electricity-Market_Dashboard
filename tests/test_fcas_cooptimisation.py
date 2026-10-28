"""The Topic 9 reference numbers, as tests.

Every number here was checked against HiGHS through scipy. The solver functions
are tested directly (no Streamlit), then the source guards, then the page.
"""
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
        for method in fc.METHODS:
            radio(app, "fc_method").set_value(method).run()
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
    for method in fc.METHODS:
        radio(app, "fc_method").set_value(method).run()
        clean(app)


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
    radio(app, "fc_method").set_value("ef").run()
    app.slider(key="fc_R").set_value(250).run()
    clean(app)
    assert "cannot find 250 MW of raise in the headroom left after the energy market" in texts(app)
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
    radio(app, "fc_method").set_value("rf").run()
    go_mode(app, 1)
    go_mode(app, 0)
    assert app.slider(key="fc_R").value == 200
    assert radio(app, "fc_method").value == "rf"


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


def test_method_bars_show_ranges_at_a_breakpoint() -> None:
    app = fresh()
    app.slider(key="fc_R").set_value(100).run()
    clean(app)
    specs = [e.proto.spec for e in app.get("plotly_chart")]
    method = next(sp for sp in specs if "Total cost of the three" in sp)
    assert "between 40 and 60" in method and "between 4 and 24" in method
    assert "between 1 and 4" in method  # reserve first
