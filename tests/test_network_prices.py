"""The Topic 7 reference tables, as tests.

Every number here was checked against HiGHS through scipy for Network mode and
against the closed form for Losses mode. B = 330^2 / 21.78 = 5000 MW/rad on
every line; G1 40 $/MWh 1500 MW, G2 20 1000, G3 50 1500.
"""
import pytest

from experiments import network_prices as np_


def cents(value):
    return pytest.approx(value, abs=0.01)


def lines(r, names):
    return [r["f"][n] for n in names]


A_LINES = ("1-2", "1-3", "2-3")
B_LINES = ("1-2", "2-3", "3-4", "1-4", "2-4")

A_CASES = [
    ({}, (), [1300, 1000, 0], [0, 1000, 1000], [40, 40, 40], 0, 72000),
    ({"2-3": 900}, (), [1000, 1000, 300], [-100, 800, 900], [40, 30, 50], 30, 75000),
    ({"2-3": 800}, (), [700, 1000, 600], [-200, 600, 800], [40, 30, 50], 30, 78000),
    ({"2-3": 400}, (), [100, 700, 1500], [-300, 100, 400], [40, 20, 60], 60, 93000),
    ({"2-3": 800}, ("1-3",), [100, 1000, 1200], [-200, None, 800], [40, 40, 50], 10, 84000),
]

B_CASES = [
    ({}, (), [1300, 1000, 0], [300, 600, 100, 1000, 700], [40, 40, 40, 40], 72000),
    ({"1-4": 700}, (), [700, 1000, 600], [0, 300, 400, 700, 700], [40, 47.5, 50, 52.5], 78000),
    ({"2-3": 500}, (), [1100, 1000, 200], [200, 500, 200, 900, 700], [40, 37.5, 50, 42.5], 74000),
    ({"2-4": 600}, (), [1500, 600, 200], [450, 450, 150, 1050, 600], [50, 20, 50, 80], 82000),
    ({"1-4": 700}, ("1-2", "2-3"), [700, 1000, 600], [None, None, 100, 700, 1000],
     [40, 50, 50, 50], 78000),
]


def _approx_lines(got, want):
    assert [g is None for g in got] == [w is None for w in want]
    assert [g for g in got if g is not None] == cents([w for w in want if w is not None])


@pytest.mark.parametrize("ratings,out,P,f,lam,sig23,cost", A_CASES)
def test_network_a(ratings, out, P, f, lam, sig23, cost) -> None:
    r = np_.solve("A", ratings, out)
    assert r["ok"]
    assert r["P"] == cents(P)
    _approx_lines(lines(r, A_LINES), f)
    assert r["lam"] == cents(lam)
    assert r["sig_up"]["2-3"] == cents(sig23)
    assert r["cost"] == cents(cost)
    assert np_.failures(np_.rules(r)) == []
    assert np_.decomposition(r)["ok"]


def test_network_a_rho() -> None:
    assert lines_rho("A", {}, (), A_LINES) == cents([0, 0, 0])
    for rating, rho in ((900, [10, -10, 10]), (800, [10, -10, 10]), (400, [20, -20, 20])):
        assert lines_rho("A", {"2-3": rating}, (), A_LINES) == cents(rho)
    radial = np_.solve("A", {"2-3": 800}, ("1-3",))
    assert [radial["rho"]["1-2"], radial["rho"]["2-3"]] == cents([0, 0])


def lines_rho(net, ratings, out, names):
    r = np_.solve(net, ratings, out)
    return [r["rho"][n] for n in names]


def test_case_b_probe_settlement_decomposition() -> None:
    dP, dcost = np_.probe("A", {"2-3": 800}, (), None, 2)
    assert dP == cents([2, 0, -1]) and dcost == pytest.approx(30, abs=1e-6)
    dP, dcost = np_.probe("A", {"2-3": 800}, (), None, 3)
    assert dP == cents([0, 0, 1]) and dcost == pytest.approx(50, abs=1e-6)
    r = np_.solve("A", {"2-3": 800})
    s = np_.settlement(r)
    assert s["consumers"] == cents(112000)
    assert s["generators"] == cents(88000)
    assert s["rent"] == s["by_flow"] == s["by_sigma"] == cents(24000)
    assert s["congestion_cost"] == cents(6000)
    d = np_.decomposition(r)
    assert d["a"]["2-3"][1] == cents(1 / 3)
    assert d["a"]["2-3"][2] == cents(-1 / 3)
    assert d["congestion"] == cents([0, -10, 10])


@pytest.mark.parametrize("ratings,out,P,f,lam,cost", B_CASES)
def test_network_b(ratings, out, P, f, lam, cost) -> None:
    r = np_.solve("B", ratings, out)
    assert r["ok"]
    assert r["P"] == cents(P)
    _approx_lines(lines(r, B_LINES), f)
    assert r["lam"] == cents(lam)
    assert r["cost"] == cents(cost)
    assert np_.failures(np_.rules(r)) == []
    assert np_.decomposition(r)["ok"]
    s = np_.settlement(r)
    assert s["rent"] == cents(s["by_flow"]) and s["rent"] == cents(s["by_sigma"])


def test_network_b_multipliers() -> None:
    r = np_.solve("B", {"1-4": 700})
    assert [r["rho"][n] for n in B_LINES] == cents([-7.5, -2.5, -2.5, 7.5, -5])
    assert r["sig_up"]["1-4"] == cents(20)
    dP, dcost = np_.probe("B", {"1-4": 700}, (), None, 4)
    assert dP == cents([-0.25, 0, 1.25]) and dcost == pytest.approx(52.5, abs=1e-6)
    assert np_.solve("B", {"2-3": 500})["sig_up"]["2-3"] == cents(20)
    assert np_.solve("B", {"2-4": 600})["sig_up"]["2-4"] == cents(120)
    star = np_.solve("B", {"1-4": 700}, ("1-2", "2-3"))
    assert [v for v in star["rho"].values() if v is not None] == cents([0, 0, 0])
    assert star["sig_up"]["1-4"] == cents(10) == star["lam"][3] - star["lam"][0]


def test_islanding_and_infeasible() -> None:
    assert not np_.islanded("B", ("1-2", "2-3"))
    assert np_.islanded("B", ("1-4", "3-4", "2-4"))
    assert not np_.solve("A", {"2-3": 400}, ("1-3",), {3: 2600})["ok"]


# --- Losses mode ------------------------------------------------------------

LOSS_CASES = [
    (0.0, 20, 0, 2300, [1300, 1000, 0], 1000, 0, 1, 40, 40, 0),
    (2e-5, 20, 0, 2300, [1320, 1000, 0], 1000, 20, 0.96, 38.40, 40, 800),
    (2e-5, 38.5, 0, 2300, [1380.08, 937.5, 0], 937.5, 17.58, 0.9625, 38.50, 40, 703.13),
    (2e-5, 20, 1500, 800, [1305, 1000, 0], -500, 5, 1.02, 40.80, 40, 200),
]


@pytest.mark.parametrize("K,c2,DA,DB,P,f,L,mlf,lamA,lamB,residue", LOSS_CASES)
def test_losses(K, c2, DA, DB, P, f, L, mlf, lamA, lamB, residue) -> None:
    r = np_.losses_nlp(K, c2, DA, DB)
    assert r["ok"]
    assert r["P"] == cents(P)
    assert r["f"] == cents(f)
    assert r["L"] == cents(L)
    assert r["MLF"] == pytest.approx(mlf, abs=1e-6)
    assert r["lamA"] == cents(lamA)
    assert r["lamB"] == cents(lamB)
    assert r["residue"] == cents(residue) == r["residue_identity"]


def test_part_v_settlement() -> None:
    r = np_.losses_nlp(2e-5, 20, 0, 2300)
    assert r["consumers"] == cents(92000)
    assert r["generators"] == cents(91200)
    assert r["discount"] == cents(1600)
    assert r["residue_identity"] == cents(800)


def test_close_call_nemde() -> None:
    r = np_.losses_nemde(2e-5, 38.5, 0, 2300, 1000)
    assert r["MLF"] == pytest.approx(0.96)
    assert r["allowance"] == cents(20)
    assert r["P"] == cents([1500, 820, 0])
    assert r["lamB"] == pytest.approx(38.5 / 0.96, abs=1e-3)
    assert r["lamA"] == cents(38.5)
    assert r["L"] == cents(13.45)
    assert r["forecast_error"] == cents(6.55)


def test_lossless_either_dispatch() -> None:
    for r in (np_.losses_nlp(0.0, 20, 0, 2300), np_.losses_nemde(0.0, 20, 0, 2300, 1000)):
        assert r["P"] == cents([1300, 1000, 0])
        assert r["f"] == cents(1000)
        assert r["lamA"] == cents(40) and r["lamB"] == cents(40)
        assert r["residue"] == cents(0)


# --- Page -------------------------------------------------------------------

def test_no_em_dashes() -> None:
    from pathlib import Path
    assert "—" not in Path(np_.__file__).read_text()
