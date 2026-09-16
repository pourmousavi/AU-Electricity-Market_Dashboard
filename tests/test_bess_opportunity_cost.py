"""The Topic 6 reference table, as tests.

Every number the battery lecture prints was checked against the two solvers
in experiments/bess_opportunity_cost.py. Delta T = 1/12, eta = 0.9 both ways,
bid 42, offer 48 unless a test says otherwise.
"""
import pytest

from experiments import bess_opportunity_cost as boc

PART_V = [40.0] * 5 + [50.0] * 7
DEMANDS = [2200.0, 2250.0, 2300.0, 2350.0, 2450.0, 2650.0,
           2700.0, 2750.0, 2700.0, 2650.0, 2600.0, 2550.0]


def cents(value):
    return pytest.approx(value, abs=0.01)


def bat(**over):
    return {**dict(P=100.0, E=30.0, E0=0.0, eta_c=0.9, eta_d=0.9, b=42.0, c=48.0),
            **over}


# --- Price path -----------------------------------------------------------

def test_part_v() -> None:
    r = boc.battery_block(PART_V, bat())
    assert r["ok"]
    assert list(r["v"][:5]) == cents([-2.2222] * 5)
    assert list(r["v"][5:]) == cents([1.8] * 7)
    assert r["bought"] == cents(33.333)
    assert r["sold"] == cents(27.0)
    assert r["cash"] == cents(16.67)
    assert r["surplus"] == cents(120.67)
    offer, bid = boc.effective(r["v"], bat())
    assert list(offer[5:]) == cents([50.0] * 7)
    assert list(bid[:5]) == cents([40.0] * 5)


def test_part_v_probes() -> None:
    base = boc.battery_block(PART_V, bat())["surplus"]
    assert boc.battery_block(PART_V, bat(), inject=(6, 1.0))["surplus"] - base == cents(1.80)
    assert boc.battery_block(PART_V, bat(), inject=(2, 1.0))["surplus"] - base == cents(-2.222)
    assert boc.battery_block(PART_V, bat(E=31.0))["surplus"] - base == cents(4.022)


def test_two_peaks() -> None:
    r = boc.battery_block([40.0] * 5 + [50, 50, 55, 55, 55, 55, 50], bat())
    assert r["Pdis"][5] == cents(0.0) and r["Pdis"][6] == cents(0.0)
    assert list(r["v"][5:]) == cents([6.3] * 7)
    assert list(boc.effective(r["v"], bat())[0][5:]) == cents([55.0] * 7)
    assert r["cash"] == cents(151.67)


def test_lossier_battery_still_dispatched() -> None:
    r = boc.battery_block(PART_V, bat(eta_c=0.85, eta_d=0.85))
    assert r["sold"] == cents(25.5)
    assert r["cash"] == cents(-136.76)
    assert r["surplus"] == cents(121.59)
    assert boc.round_trip(PART_V, bat(eta_c=0.85, eta_d=0.85)) == (
        cents(1.25), cents(1.384), False)


def test_negative_price_complementarity() -> None:
    prices = [-50.0] + [50.0] * 11
    r = boc.battery_block(prices, bat(E0=30.0))
    assert r["Pch"][0] == cents(100.0)
    assert r["Pdis"][0] == cents(81.0)
    assert r["surplus"] == cents(159.17)
    assert r["cash"] == cents(1429.17)
    assert boc.both_taps(r) == [0]
    m = boc.battery_block(prices, bat(E0=30.0), binary=True)
    assert m["v"] is None
    assert min(m["Pch"][0], m["Pdis"][0]) == cents(0.0)
    assert m["surplus"] == cents(54.0)
    assert boc.both_taps(m) == []


def test_q4_six_intervals() -> None:
    r = boc.battery_block([50.0, 50.0, 55.0, 55.0, 55.0, 55.0], bat(E0=20.0))
    assert r["Pdis"][0] == cents(0.0) and r["Pdis"][1] == cents(0.0)
    assert list(r["v"]) == cents([6.3] * 6)
    assert boc.effective(r["v"], bat())[0][0] == cents(55.0)


# --- Market mode ----------------------------------------------------------

def test_market_no_battery() -> None:
    r = boc.market(DEMANDS, bat(P=0.0, E=0.0))
    assert r["ok"]
    assert list(r["lam"]) == cents([40.0] * 5 + [50.0] * 7)
    assert r["gen_cost"] == cents(81416.67)
    assert r["consumers"] == cents(116000.0)
    assert list(r["rents"]) == cents([8750.0, 25833.33, 0.0])


def test_market_price_taker() -> None:
    r = boc.market(DEMANDS, bat())
    assert list(r["lam"]) == cents([40.0] * 5 + [50.0] * 7)
    assert r["gen_cost"] == cents(81400.0)
    assert r["cash"] == cents(16.67)
    assert r["consumers"] == cents(116000.0)
    assert list(r["v"][:5]) == cents([-2.2222] * 5)
    assert list(r["v"][5:]) == cents([1.8] * 7)


def test_market_price_maker() -> None:
    r = boc.market(DEMANDS, bat(P=300.0, E=90.0))
    assert r["lam"][0] == cents(40.0)
    assert list(r["lam"][1:5]) == cents([43.62] * 4)
    assert list(r["lam"][5:]) == cents([50.0] * 7)
    assert r["gen_cost"] == cents(81377.08)
    assert r["consumers"] == cents(118820.58)
    assert r["cash"] == cents(-156.50)
    assert list(r["rents"]) == cents([10560.0, 27040.0, 0.0])
    assert list(r["v"]) == cents([1.8] * 12)
