"""The Topic 5 verification table, as tests.

Every row of the table in the Topic 5 experiment brief is one assertion here.
The app must reproduce these numbers exactly before it is deployed, because
two of the three experiments are driven live in the review forum against a
deck that already prints them.
"""
from pathlib import Path

import pytest

from experiments import ed_price, ed_ramp, truthful_offers
from experiments._kit import ed

ROOT = Path(__file__).resolve().parent.parent
RAMP_DEMANDS = [2600.0, 2540.0, 2450.0]
RAMP_LIMITS = [45.0, 20.0, 40.0]


def approx(value):
    return pytest.approx(value, abs=1e-6)


# --- ed_price -------------------------------------------------------------

def test_ed_price_case_one() -> None:
    """D = 2600: P = (1500, 1000, 100), lambda = 50, mu-bar = (10, 30, 0)."""
    r = ed.solve([2600.0])
    assert r.ok
    assert r.P[0] == approx((1500.0, 1000.0, 100.0))
    assert r.lam[0] == approx(50.0)
    assert r.cost[0] == pytest.approx(7083.33, abs=0.005)
    assert r.mu_max[0] == approx((10.0, 30.0, 0.0))
    assert r.mu_min[0] == approx((0.0, 0.0, 0.0))


@pytest.mark.parametrize("demand,expected", [(2400.0, 40.0), (900.0, 20.0)])
def test_ed_price_staircase_treads(demand: float, expected: float) -> None:
    assert ed.solve([demand]).lam[0] == approx(expected)


def test_ed_price_riser_is_not_unique() -> None:
    """At D = 2500 the one-MW test gives 40 $/h below and 50 $/h above."""
    base = ed.solve([2500.0]).cost[0]
    above = (ed.solve([2501.0]).cost[0] - base) * ed.PER_HOUR
    below = (base - ed.solve([2499.0]).cost[0]) * ed.PER_HOUR
    assert below == approx(40.0)
    assert above == approx(50.0)
    assert abs(above - below) > 1e-6  # what raises the non-unique banner


def test_ed_price_forced_on() -> None:
    """G1 minimum 500 with D = 600 puts a mu-underbar on two rows."""
    r = ed.solve([600.0], [500.0, 0.0, 0.0])
    assert r.ok
    assert r.P[0] == approx((500.0, 100.0, 0.0))
    assert r.lam[0] == approx(20.0)
    assert r.mu_min[0][0] == approx(20.0)
    assert r.mu_min[0][2] == approx(30.0)


def test_staircase_matches_the_solver() -> None:
    """The closed-form staircase is what the chart draws, so pin it to the LP.

    Checked strictly inside each tread, where exactly one generator is marginal
    and the price is therefore unique. The risers are covered separately by
    test_ed_price_riser_is_not_unique, and the very bottom of the staircase by
    the test below it.
    """
    for lo, hi, price in ed.staircase():
        for demand in (lo + 1, (lo + hi) / 2, hi - 1):
            solved = ed.solve([float(demand)])
            assert solved.ok
            assert solved.lam[0] == approx(price), demand
            assert ed.price_at(float(demand)) == approx(price)
    assert ed.price_at(4001.0) is None


def test_zero_demand_has_no_marginal_generator() -> None:
    """At D = 0 every unit sits on its lower bound, so lambda is not pinned.

    HiGHS returns 0, which is a valid dual (0 = 20 - 20 on G2's row). The page
    shows what the solver returns and the one-megawatt test flags it, rather
    than pretending the cheapest offer is the price.
    """
    solved = ed.solve([0.0])
    assert solved.ok
    assert solved.lam[0] == approx(0.0)
    assert ed.solve([1.0]).lam[0] == approx(20.0)


def test_ed_price_above_total_capacity_is_infeasible() -> None:
    r = ed.solve([4100.0])
    assert not r.ok
    assert "Infeasible" in r.message


# --- ed_ramp --------------------------------------------------------------

def test_ed_ramp_ramps_off() -> None:
    r = ed.solve(RAMP_DEMANDS)
    assert r.ok
    assert r.lam == approx((50.0, 50.0, 40.0))
    assert r.cost[0] == pytest.approx(7083.33, abs=0.005)
    assert r.cost[1] == pytest.approx(6833.33, abs=0.005)
    assert r.cost[2] == pytest.approx(6500.00, abs=0.005)
    assert r.total_cost == pytest.approx(20416.67, abs=0.005)
    assert r.payment(RAMP_DEMANDS) == pytest.approx(29583.33, abs=0.005)


def test_ed_ramp_off_separates_the_horizon() -> None:
    """With no ramp row, solving alone and solving together must agree."""
    alone = ed.solve(RAMP_DEMANDS)
    together = ed.solve(RAMP_DEMANDS, ramps=None)
    assert alone.P == together.P
    assert alone.lam == approx(together.lam)


def test_ed_ramp_ramps_on() -> None:
    r = ed.solve(RAMP_DEMANDS, ramps=RAMP_LIMITS)
    assert r.ok
    assert r.P[0] == approx((1500.0, 1000.0, 100.0))
    assert r.P[1] == approx((1480.0, 1000.0, 60.0))
    assert r.P[2] == approx((1435.0, 995.0, 20.0))
    assert r.lam == approx((70.0, 60.0, 20.0))
    assert r.total_cost == pytest.approx(20458.33, abs=0.005)
    assert r.payment(RAMP_DEMANDS) == pytest.approx(31950.00, abs=0.005)


def test_ed_ramp_binding_rows() -> None:
    """G3 down t1-t2 is 20, G1 down t2-t3 is 20, G3 down t2-t3 is 30."""
    r = ed.solve(RAMP_DEMANDS, ramps=RAMP_LIMITS)
    binding = {
        (f"{gen.name} {way} t{step + 1}-t{step + 2}", round(nu, 6))
        for step in range(len(r.nu_up))
        for k, gen in enumerate(ed.GENERATORS)
        for nu, way in ((r.nu_up[step][k], "up"), (r.nu_dn[step][k], "down"))
        if nu > 1e-6
    }
    assert binding == {
        ("G3 down t1-t2", 20.0),
        ("G1 down t2-t3", 20.0),
        ("G3 down t2-t3", 30.0),
    }


@pytest.mark.parametrize("interval,expected", [(1, 70.0), (2, 60.0), (3, 20.0)])
def test_ed_ramp_one_megawatt_probe(interval: int, expected: float) -> None:
    base = ed.solve(RAMP_DEMANDS, ramps=RAMP_LIMITS)
    probed = list(RAMP_DEMANDS)
    probed[interval - 1] += 1.0
    after = ed.solve(probed, ramps=RAMP_LIMITS)
    assert (after.total_cost - base.total_cost) * ed.PER_HOUR == approx(expected)
    assert base.lam[interval - 1] == approx(expected)


def test_ed_ramp_probe_chain_at_t1() -> None:
    """The chain the page itemises: G3 up in all three, G1 down in t2 and t3."""
    base = ed.solve(RAMP_DEMANDS, ramps=RAMP_LIMITS)
    after = ed.solve([2601.0, 2540.0, 2450.0], ramps=RAMP_LIMITS)
    moves = {
        (t, ed.GENERATORS[k].name): round(after.P[t][k] - base.P[t][k], 6)
        for t in range(3) for k in range(3)
        if abs(after.P[t][k] - base.P[t][k]) > 1e-6
    }
    assert moves == {
        (0, "G3"): 1.0,
        (1, "G3"): 1.0, (1, "G1"): -1.0,
        (2, "G3"): 1.0, (2, "G1"): -1.0,
    }


# --- truthful_offers ------------------------------------------------------

@pytest.mark.parametrize("scenario,price", [
    (truthful_offers.HIGH, 50.0),
    (truthful_offers.MILD, 40.0),
])
def test_truthful_offers_scenario_prices(scenario: str, price: float) -> None:
    assert ed.price_at(truthful_offers.SCENARIOS[scenario]) == approx(price)


@pytest.mark.parametrize("demand,offer,expected", [
    (2600.0, 45.0, 250.0),    # high day, offer 45: dispatched, +250 $/h
    (2200.0, 38.0, -250.0),   # mild day, offer 38: dispatched, -250 $/h
    (2200.0, 45.0, 0.0),      # mild day, offer 45: not dispatched, 0
])
def test_truthful_offers_profit(demand: float, offer: float,
                                expected: float) -> None:
    price = ed.price_at(demand)
    assert truthful_offers._profit(offer, price) == approx(expected)


def test_truthful_offers_marginal_offer_picks_no_side() -> None:
    assert truthful_offers._profit(50.0, 50.0) is None


def test_true_cost_is_never_worse_on_either_day() -> None:
    """The point of the experiment, checked over every offer on the slider."""
    for demand in truthful_offers.SCENARIOS.values():
        price = ed.price_at(demand)
        truthful = truthful_offers._profit(truthful_offers.G4_COST, price)
        truthful = 0.0 if truthful is None else truthful
        for offer in range(0, 101):
            other = truthful_offers._profit(float(offer), price)
            other = 0.0 if other is None else other
            assert truthful >= other - 1e-9, (demand, offer)


# --- Presentation rules ---------------------------------------------------

TOPIC5_SOURCES = (
    ROOT / "experiments" / "_kit" / "ed.py",
    ROOT / "experiments" / "ed_price.py",
    ROOT / "experiments" / "ed_ramp.py",
    ROOT / "experiments" / "truthful_offers.py",
)

BANNED = ("—", "4087", "7087", "The University of Adelaide", '"tight"',
          "is tight", "are tight")


@pytest.mark.parametrize("path", TOPIC5_SOURCES, ids=lambda p: p.name)
def test_no_em_dashes_or_legacy_branding(path: Path) -> None:
    text = path.read_text()
    for banned in BANNED:
        assert banned not in text, f"{path.name} contains {banned!r}"


ALLOWED_COLOURS = {ed.NAVY, ed.PURPLE, ed.LAVENDER, ed.SILVER, ed.LIMESTONE,
                   ed.MUTED, "#FFFFFF"}


@pytest.mark.parametrize("path", TOPIC5_SOURCES, ids=lambda p: p.name)
def test_only_palette_colours(path: Path) -> None:
    import re
    found = set(re.findall(r"#[0-9A-Fa-f]{6}", path.read_text()))
    assert found <= ALLOWED_COLOURS, f"{path.name} uses {found - ALLOWED_COLOURS}"


def test_presets_stay_inside_their_widget_ranges() -> None:
    """A preset landing outside a slider range takes the whole page down."""
    for values in ed_price.PRESETS.values():
        assert 0 <= values[ed_price.DEMAND_KEY] <= 4200
        for k, key in enumerate(ed_price.MIN_KEYS):
            assert 0 <= values[key] <= ed.GENERATORS[k].capacity
    for key, value in ed_ramp.DEFAULTS.items():
        if key in ed_ramp.DEMAND_KEYS:
            assert 0 <= value <= 4000
        elif key in ed_ramp.RAMP_KEYS:
            assert 1 <= value <= 1500


# --- LaTeX rendering -------------------------------------------------------
#
# Streamlit parses `$...$` on markdown TEXT nodes. A block-level tag opens an
# HTML block that runs to the next blank line, and everything inside it is one
# opaque node, so maths written there renders as its own source. These two
# tests pin the two places that rule bites.

def test_marker_span_stays_inline_so_latex_still_renders() -> None:
    """The box marker must share its line with the prose, not sit alone."""
    import re
    from streamlit.testing.v1 import AppTest

    harness = (
        f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
        "import importlib\n"
        "importlib.import_module('experiments.ed_price').render()\n"
    )
    app = AppTest.from_string(harness, default_timeout=180).run()
    marked = [m.value for m in app.markdown
              if m.value.startswith('<span class="ed-mark')]
    assert marked, "no marked boxes rendered at all"
    for value in marked:
        assert re.match(r'^<span class="ed-mark[^"]*"></span>\S', value), (
            "a marker span alone on its line opens an HTML block and would "
            f"swallow the maths after it: {value[:80]!r}"
        )


def test_the_html_table_uses_unicode_not_latex() -> None:
    """The one real HTML block on these pages cannot carry LaTeX, so it must
    not try: its symbols are the Unicode letters, defined in LaTeX alongside."""
    from experiments import ed_ramp

    table = ed_ramp._plan_table(
        ed.solve(RAMP_DEMANDS, ramps=RAMP_LIMITS),
        RAMP_DEMANDS, RAMP_LIMITS, flag=False,
    )
    assert "<table>" in table
    for command in ("\\lambda", "\\mu", "\\nu", "\\Delta", "\\text"):
        assert command not in table, f"{command} would render as its own source"
    assert ed.LAMBDA in table
