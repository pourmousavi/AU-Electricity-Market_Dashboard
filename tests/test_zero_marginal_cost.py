"""The Topic 10 reference numbers, as tests.

The solver functions are tested directly (no Streamlit), then the source guards,
then the page. "Unique" means the left and right 1 MW changes in cost agree.
"""
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from experiments import zero_marginal_cost as zm
from experiments._kit import ed

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "experiments" / "zero_marginal_cost.py"


def approx(x, tol=1e-6):
    return pytest.approx(x, abs=tol)


def is_unique(s) -> bool:
    return zm.unique(s["lam_left"], s["lam_right"])


def units(s):
    return [u["P"] for u in s["units"]]


def mus(s):
    return [u["mu_lo"] for u in s["units"]]


# --- Mode 1 -----------------------------------------------------------------

def test_forum_defaults() -> None:
    s = zm.mode1("forum", 700, -30)
    assert s["lam"] == approx(-30) and is_unique(s)
    assert units(s) == approx([300, 200]) and s["PW"] == approx(600)
    assert s["curtailed"] == approx(100)
    assert mus(s) == approx([50, 80])
    assert s["case"] == "B"
    assert zm.m1_setter_sentence(s).endswith("(case B).")


def test_forum_minimums_off() -> None:
    s = zm.mode1("forum", 700, -30, minimums=False)
    assert s["lam"] == approx(20) and is_unique(s)
    assert units(s) == approx([400, 0]) and s["PW"] == approx(700)
    assert s["case"] == "A"
    assert zm.m1_setter_sentence(s) == "Set by A's offer."


def test_forum_no_wind() -> None:
    s = zm.mode1("forum", 0, -30)
    assert s["lam"] == approx(50) and is_unique(s)
    assert units(s) == approx([800, 300])
    assert s["case"] is None


def _steps(preset, cW, minimums):
    return [(round(p, 6), e) for p, e in zm.curve_steps(zm.mode1_curve(preset, cW, minimums))]


def test_forum_curves() -> None:
    assert _steps("forum", -30, True) == [(50, 100), (20, 600), (-30, None)]
    assert _steps("forum", -30, False) == [(50, 300), (20, 1100), (-30, None)]


def test_forum_curve_sentence() -> None:
    on = zm.curve_steps(zm.mode1_curve("forum", -30, True))
    off = zm.curve_steps(zm.mode1_curve("forum", -30, False))
    assert zm.curve_sentence(on, off, -30) == (
        r"With minimums: 50 \$/MWh up to 100 MW of wind, 20 \$/MWh up to 600 MW, then the wind "
        "offer. Without minimums the same steps come at 300 and 1100 MW: inflexibility brings "
        "the negative price forward.")


@pytest.mark.parametrize("W, left, right", [(100, 20, 50), (600, -30, 20)])
def test_forum_breakpoints_are_ranges(W, left, right) -> None:
    s = zm.mode1("forum", W, -30)
    assert not is_unique(s)
    assert s["lam_left"] == approx(left) and s["lam_right"] == approx(right)
    assert zm.m1_setter_sentence(s) is None
    lo, hi = sorted((left, right))
    assert zm.price_text(s["lam_left"], s["lam_right"]) == (
        f"between {zm._n(lo)} and {zm._n(hi)} $/MWh")


@pytest.mark.parametrize("cW, mua, mub", [(0, 20, 50), (-60, 80, 110)])
def test_forum_wind_offer_moves_the_price_only(cW, mua, mub) -> None:
    s = zm.mode1("forum", 700, cW)
    assert s["lam"] == approx(cW) and is_unique(s)
    assert mus(s) == approx([mua, mub])
    assert units(s) == approx([300, 200]) and s["PW"] == approx(600)


def test_lecture_defaults() -> None:
    s = zm.mode1("lecture", 1600, -40)
    assert s["lam"] == approx(-40) and is_unique(s)
    assert units(s) == approx([600, 500]) and s["PW"] == approx(1300)
    assert s["curtailed"] == approx(300)
    assert mus(s) == approx([80, 60])


def test_lecture_curves() -> None:
    assert _steps("lecture", 0, True) == [(40, 800), (20, 1300), (0, None)]
    assert _steps("lecture", 0, False) == [(40, 1400), (20, 2400), (0, None)]


# --- Mode 2 -----------------------------------------------------------------

def test_forum_day_defaults() -> None:
    s = zm.mode2("forum", 190, 400)
    assert s["lam"] == approx([400, 400]) and s["v"] == approx([400, 400])
    assert all(zm.unique(a, b) for a, b in zip(s["lam_left"], s["lam_right"]))
    assert s["dis"] == approx([150, 40]) and s["DR"] == approx([0, 110])
    assert s["O"] == approx([150, 150])
    assert s["setter"] == ["battery at its opportunity cost (displaces demand response at 19:00)",
                           "demand response"]
    assert s["rev_battery"] == approx(76000) and s["cost"] == approx(80000)
    assert zm.usd(s["rev_battery"]) == "$76000" and zm.usd(s["cost"]) == "$80000"


def test_forum_day_400() -> None:
    s = zm.mode2("forum", 400, 400)
    assert s["lam"] == approx([120, 120]) and s["v"] == approx([0, 0])
    assert s["dis"] == approx([200, 200]) and s["O"] == approx([100, 100])
    assert s["setter"] == ["OCGT", "OCGT"]
    assert s["rev_battery"] == approx(48000) and s["cost"] == approx(24000)


def test_forum_day_299_and_300() -> None:
    s = zm.mode2("forum", 299, 400)
    assert s["lam"] == approx([400, 400]) and s["rev_battery"] == approx(119600)
    s = zm.mode2("forum", 300, 400)
    assert s["lam_left"] == approx([120, 120]) and s["lam_right"] == approx([400, 400])
    assert not any(zm.unique(a, b) for a, b in zip(s["lam_left"], s["lam_right"]))


@pytest.mark.parametrize("cDR, lam, rev", [(300, 300, 57000), (500, 500, 95000)])
def test_forum_day_dr_bid(cDR, lam, rev) -> None:
    s = zm.mode2("forum", 190, cDR)
    assert s["lam"] == approx([lam, lam]) and s["rev_battery"] == approx(rev)


def test_lecture_day_defaults() -> None:
    s = zm.mode2("lecture", 800, 300)
    assert s["lam"] == approx([0, 0, 0, 0, 110, 300, 300, 300])
    assert s["v"] == approx([0, 0, 0, 0, 104.5, 285, 285, 285])
    assert all(zm.unique(a, b) for a, b in zip(s["lam_left"], s["lam_right"]))
    # The charging split between 11:00 and 13:00 is not unique; the totals are.
    assert round(sum(s["ch"]), 1) == 842.1 and sum(s["dis"]) == approx(760)
    battery = "battery at its opportunity cost (displaces demand response at 16:00)"
    assert s["setter"] == ["solar (curtailed)"] * 4 + ["OCGT", "demand response", battery, battery]
    assert s["rev_battery"] == approx(228000) and s["cost"] == approx(122000)
    assert s["margin_ocgt"] == approx(182400)
    assert s["capture_solar"] == approx(46.62, 0.005)
    assert s["capture_wind"] == approx(148.66, 0.005)
    assert s["avg_price"] == approx(126.25)


def test_lecture_day_1600() -> None:
    s = zm.mode2("lecture", 1600, 300)
    assert s["lam"] == approx([0, 0, 0, 0, 0, 110, 110, 110])
    assert s["rev_battery"] == approx(132000) and s["cost"] == approx(61600)
    assert s["capture_solar"] == approx(9.59, 0.005) and s["avg_price"] == approx(41.25)


def test_lecture_sweep() -> None:
    rev = {E: r for E, r, _ in zm.mode2_sweep("lecture", 300)}
    assert sorted(rev) == list(range(500, 2001, 100))
    expected = {500: 142500, 800: 228000, 900: 94050, 1200: 125400}
    expected.update({E: 132000 for E in range(1400, 2001, 100)})
    for E, r in expected.items():
        assert rev[E] == approx(r), E


@pytest.mark.parametrize("cDR, lam, v, rev", [(200, 200, 190, 152000), (400, 400, 380, 304000)])
def test_lecture_day_dr_bid(cDR, lam, v, rev) -> None:
    s = zm.mode2("lecture", 800, cDR)
    assert s["lam"][5:] == approx([lam] * 3) and s["v"][5:] == approx([v] * 3)
    assert s["rev_battery"] == approx(rev)


def test_number_style() -> None:
    assert zm._n(-30) == "−30" and zm._n(104.5) == "104.5" and zm._n(46.6234) == "46.62"
    assert zm.usd(228000) == "$228000"
    assert zm.price_text(-30, -30) == "−30 $/MWh"
    assert zm.price_text(120, 400) == "between 120 and 400 $/MWh"


# --- Source guards ----------------------------------------------------------

BANNED = ("—", "4087", "7087", "The University of Adelaide", "Workshop", "workshop")
ALLOWED_COLOURS = {ed.NAVY, ed.PURPLE, ed.LAVENDER, ed.SILVER, ed.LIMESTONE, ed.MUTED, "#FFFFFF"}


def test_no_banned_strings() -> None:
    text = SOURCE.read_text()
    for banned in BANNED:
        assert banned not in text, f"zero_marginal_cost.py contains {banned!r}"


def test_only_palette_colours() -> None:
    found = set(re.findall(r"#[0-9A-Fa-f]{6}", SOURCE.read_text()))
    assert found <= ALLOWED_COLOURS, found - ALLOWED_COLOURS


def test_every_key_has_the_zm_prefix() -> None:
    text = SOURCE.read_text()
    keys = re.findall(r"""key=f?["']([^"']*)["']""", text)
    keys += re.findall(r"""_kept\(\s*f?["']([^"']*)["']""", text)
    keys += re.findall(r"""_put\(\s*f?["']([^"']*)["']""", text)
    assert keys
    assert all(k.startswith("zm_") for k in keys), keys
    assert all(k.startswith("zm_") for k in zm.DEFAULTS)
    assert "set_page_config" not in text
    assert "use_container_width" not in text
    assert "STATE_GROUP" not in text


def test_pure_section_has_no_streamlit_calls() -> None:
    body = SOURCE.read_text().split("# Pure helpers")[1].split("# Charts")[0]
    assert not re.search(r"(?<![\w.])st\.", body)


# --- Page -------------------------------------------------------------------

HARNESS = (
    "import sys\n"
    f"sys.path.insert(0, {str(ROOT)!r})\n"
    "from experiments import zero_marginal_cost\n"
    "zero_marginal_cost.render()\n"
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


def test_every_mode_and_preset_renders() -> None:
    app = fresh()
    clean(app)
    for preset in zm.M1_PRESETS:
        radio(app, "zm_m1_preset").set_value(preset).run()
        clean(app)
        app.toggle(key="zm_min").set_value(False).run()
        clean(app)
    radio(app, "zm_mode").set_value(zm.MODES[1]).run()
    clean(app)
    for preset in zm.M2_PRESETS:
        radio(app, "zm_m2_preset").set_value(preset).run()
        clean(app)


def test_mode_one_default_numbers() -> None:
    app = fresh()
    text = texts(app)
    assert "−30 $/MWh" in text
    assert "20 − (−30) = 50" in text and "50 − (−30) = 80" in text
    assert "Wind dispatched 600 MW, curtailed 100 MW." in text
    assert "inflexibility brings the negative price forward" in text


def test_mode_one_breakpoint_shows_a_range() -> None:
    app = fresh()
    app.slider(key="zm_W").set_value(100).run()
    text = texts(app)
    assert "between 20 and 50 $/MWh" in text
    assert zm.RANGE_SENTENCE in text


def test_mode_two_forum_numbers_and_range() -> None:
    app = fresh()
    radio(app, "zm_mode").set_value(zm.MODES[1]).run()
    text = texts(app)
    assert "$76000" in text and "$80000" in text
    assert "battery at its opportunity cost (displaces demand response at 19:00)" in text
    app.slider(key="zm_EB").set_value(300).run()
    clean(app)
    text = texts(app)
    assert "between 120 and 400" in text and zm.RANGE_SENTENCE in text


def test_preset_change_resets_the_knobs() -> None:
    app = fresh()
    app.slider(key="zm_W").set_value(1200).run()
    app.slider(key="zm_cW").set_value(0).run()
    radio(app, "zm_m1_preset").set_value("lecture").run()
    assert app.slider(key="zm_W").value == 1600 and app.slider(key="zm_cW").value == -40
    radio(app, "zm_mode").set_value(zm.MODES[1]).run()
    app.slider(key="zm_EB").set_value(400).run()
    radio(app, "zm_m2_preset").set_value("lecture").run()
    assert app.slider(key="zm_EB").value == 800 and app.slider(key="zm_DR").value == 300
    radio(app, "zm_mode").set_value(zm.MODES[0]).run()
    assert radio(app, "zm_m1_preset").value == "lecture"
    assert app.slider(key="zm_W").value == 1600
