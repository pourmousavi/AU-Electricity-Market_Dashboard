"""Energy and FCAS co-optimisation (Topic 9).

Four modes, all single five-minute intervals on a copper plate, in actual units:
MW, $/MWh for energy, $/MW/h for FCAS and $/h for cost rates. One interval costs
one twelfth of each rate.

1. Co-optimise energy and contingency raise. Energy and reserve share each
   unit's capacity row P_k + r+_k <= Pbar_k, so the reserve price is the offer
   plus the energy margin the unit gives up. Three clearing methods are solved:
   one LP, energy first, and reserve first.
2. FCAS trapeziums for several services, with regulation sharing the headroom
   with contingency services (Part IV slide 8).
3. Lower services, where the opportunity cost flips sign.
4. Global and local requirements, where a regional price is the sum of the
   multipliers of every requirement row that covers the region.

Every LP is solved with scipy's HiGHS through linprog. Sign conventions
(scipy, minimisation): eqlin.marginals[i] = d(cost)/d(b_eq[i]); ineqlin.marginals[i]
= d(cost)/d(b_ub[i]), which is never positive. A ">=" row is written as
"-row <= -rhs", so its multiplier is -ineqlin.marginals.

P_k has no separate upper bound in the raise LP: the capacity row is the only
upper limit. A separate bound would split the capacity multiplier between the
bound and the row and make the "who holds reserve and why" numbers wrong.

A price is the left and right change in optimal cost for a 1 MW change in the
right-hand side (_range). Where the two differ the price is not unique, and the
page shows the range instead of one solver multiplier. Students only move the
knobs listed on each page; every preset is fixed in code.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy.optimize import linprog

from experiments._kit import ed

EPS = 1e-6
LAMBDA = ed.LAMBDA
PI = "π"

# ---------------------------------------------------------------- presets
RAISE_PRESETS = {
    "forum": {
        "label": "Review forum Q3: units A, B and C",
        "D": 800.0, "R_default": 150.0, "R_max": 400.0,
        "units": [
            dict(name="A", tech="coal", c=20.0, Pmin=0.0, Pmax=500.0, RR=100.0, cp=1.0),
            dict(name="B", tech="CCGT", c=40.0, Pmin=0.0, Pmax=400.0, RR=200.0, cp=4.0),
            dict(name="C", tech="gas", c=60.0, Pmin=0.0, Pmax=300.0, RR=100.0, cp=30.0),
        ],
    },
    "lecture": {
        "label": "Lecture example: G1, G2 and G3 (Part III)",
        "D": 2800.0, "R_default": 300.0, "R_max": 1100.0,
        "units": [
            dict(name="G1", tech="CCGT", c=40.0, Pmin=600.0, Pmax=1500.0, RR=450.0, cp=2.0),
            dict(name="G2", tech="coal", c=20.0, Pmin=500.0, Pmax=1000.0, RR=150.0, cp=1.0),
            dict(name="G3", tech="gas", c=50.0, Pmin=450.0, Pmax=1500.0, RR=500.0, cp=15.0),
        ],
    },
}
BATTERY_RAISE_OFFER = 1.0   # $/MW/h, idle battery, energy target fixed at 0 MW


def _raise_lp(units, D, R, batt_mw=0.0, fix_P=None, fix_r=None):
    """Joint energy + contingency raise LP. Variables: P_k, r_k, r_B.
    fix_P / fix_r: optional fixed values (used by the sequential methods).
    P_k has NO separate upper bound: the capacity row P_k + r_k <= Pmax is the
    only upper limit, as on the lecture slide. A separate bound would split the
    capacity multiplier between the bound and the row and make mu_bar ambiguous."""
    n = len(units)
    nv = 2 * n + 1
    c = [u["c"] for u in units] + [u["cp"] for u in units] + [BATTERY_RAISE_OFFER]
    A_eq = np.zeros((1, nv)); A_eq[0, :n] = 1.0; b_eq = [D]
    A_ub, b_ub = [], []
    for k, u in enumerate(units):                     # capacity rows  [mu_bar_k]
        row = np.zeros(nv); row[k] = 1.0; row[n + k] = 1.0
        A_ub.append(row); b_ub.append(u["Pmax"])
    row = np.zeros(nv); row[n:] = -1.0                # requirement row [pi_plus]
    A_ub.append(row); b_ub.append(-R)
    bounds = []
    for k, u in enumerate(units):
        lo, hi = u["Pmin"], None
        if fix_P is not None: lo = hi = fix_P[k]
        bounds.append((lo, hi))
    for k, u in enumerate(units):
        lo, hi = 0.0, u["RR"]
        if fix_r is not None: lo = hi = fix_r[k]
        bounds.append((lo, hi))
    bounds.append((0.0, batt_mw if fix_r is None else fix_r[n]))
    res = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if res.status != 0:
        return None
    return dict(P=res.x[:n], r=res.x[n:2 * n], rB=res.x[2 * n], cost=res.fun,
                lam=res.eqlin.marginals[0], pi=-res.ineqlin.marginals[n],
                mubar=[-m for m in res.ineqlin.marginals[:n]])


def _range(f, x, h=1.0):
    """Left and right derivative of the optimal cost: the price range."""
    base = f(x)
    up, dn = f(x + h), f(x - h)
    right = None if (base is None or up is None) else (up - base) / h
    left = None if (base is None or dn is None) else (base - dn) / h
    return left, right


def cooptimise(preset, R, batt_mw=0.0):
    p = RAISE_PRESETS[preset]; units, D = p["units"], p["D"]
    s = _raise_lp(units, D, R, batt_mw)
    if s is None:
        return None
    cost = lambda d=D, r=R: (lambda z: None if z is None else z["cost"])(_raise_lp(units, d, r, batt_mw))
    s["lam_range"] = _range(lambda d: cost(d=d), D)
    s["pi_range"] = _range(lambda r: cost(r=r), R)
    # each unit's full cost of a MW of reserve: offer + value of its capacity
    s["reserve_cost"] = [u["cp"] + mb for u, mb in zip(units, s["mubar"])]
    return s


def energy_first(preset, R, batt_mw=0.0):
    p = RAISE_PRESETS[preset]; units, D = p["units"], p["D"]
    e = _raise_lp(units, D, 0.0, 0.0)                 # step 1: energy only
    if e is None: return None
    s = _raise_lp(units, D, R, batt_mw, fix_P=e["P"])   # step 2: reserve from what is left
    if s is None: return dict(feasible=False, P=e["P"], lam=e["lam"])
    pi_rng = _range(lambda r: (lambda z: None if z is None else z["cost"])(
        _raise_lp(units, D, r, batt_mw, fix_P=e["P"])), R)
    return dict(feasible=True, P=e["P"], r=s["r"], rB=s["rB"], lam=e["lam"], pi=s["pi"],
                pi_range=pi_rng, cost=s["cost"])


def reserve_first(preset, R, batt_mw=0.0):
    p = RAISE_PRESETS[preset]; units, D = p["units"], p["D"]
    n = len(units)
    # step 1: reserve only, from each unit's full room above its minimum
    c = [u["cp"] for u in units] + [BATTERY_RAISE_OFFER]
    bounds = [(0.0, min(u["RR"], u["Pmax"] - u["Pmin"])) for u in units] + [(0.0, batt_mw)]
    res = linprog(c, A_ub=[[-1.0] * (n + 1)], b_ub=[-R], bounds=bounds, method="highs")
    if res.status != 0: return None
    r = res.x
    # step 2: energy with that reserve held back
    e = _raise_lp(units, D, 0.0, 0.0, fix_r=list(r[:n]) + [r[n]])
    if e is None: return dict(feasible=False, r=r[:n], rB=r[n], pi=-res.ineqlin.marginals[0])
    cost = float(np.dot([u["c"] for u in units], e["P"]) + np.dot(c, r))
    return dict(feasible=True, P=e["P"], r=r[:n], rB=r[n], lam=e["lam"],
                pi=-res.ineqlin.marginals[0], cost=cost)


def sweep(preset, batt_mw=0.0, step=1.0):
    p = RAISE_PRESETS[preset]
    out = []
    for R in np.arange(0.0, p["R_max"] + 1e-9, step):
        s = _raise_lp(p["units"], p["D"], R, batt_mw)
        if s is None: break
        out.append((R, s["pi"], s["lam"]))
    return out


# ------------------------------------------------------- lower service (add-on b)
LOWER_PRESETS = {
    "forum_midday": {
        "label": "Review forum: sunny midday",
        "D": 1000.0, "R_default": 30.0, "R_max": 50.0,
        "units": [
            dict(name="Solar", c=25.0, Pmin=0.0, Pmax=2000.0, RRlow=0.0, cm=0.0),
            dict(name="Gas", c=70.0, Pmin=200.0, Pmax=500.0, RRlow=50.0, cm=2.0),
        ],
    },
    "lecture_midday": {
        "label": "Lecture example: Topic 8 midday trough (Part IV slide 4)",
        "D": 1500.0, "R_default": 50.0, "R_max": 150.0,
        "units": [
            dict(name="G1", c=40.0, Pmin=600.0, Pmax=1500.0, RRlow=150.0, cm=1.0),
            dict(name="G2", c=20.0, Pmin=500.0, Pmax=1000.0, RRlow=0.0, cm=0.0),
        ],
    },
}


def lower_lp(preset, Rm, D=None):
    p = LOWER_PRESETS[preset]; units = p["units"]; D = p["D"] if D is None else D
    n = len(units)
    c = [u["c"] for u in units] + [u["cm"] for u in units]
    A_eq = np.zeros((1, 2 * n)); A_eq[0, :n] = 1.0
    A_ub, b_ub = [], []
    for k, u in enumerate(units):                       # floor rows: P - r >= Pmin
        row = np.zeros(2 * n); row[k] = -1.0; row[n + k] = 1.0
        A_ub.append(row); b_ub.append(-u["Pmin"])
    row = np.zeros(2 * n); row[n:] = -1.0; A_ub.append(row); b_ub.append(-Rm)
    bounds = [(0.0, u["Pmax"]) for u in units] + [(0.0, u["RRlow"]) for u in units]   # floor rows carry Pmin
    res = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=A_eq, b_eq=[D], bounds=bounds, method="highs")
    if res.status != 0: return None
    return dict(P=res.x[:n], r=res.x[n:], cost=res.fun, lam=res.eqlin.marginals[0],
                pi=-res.ineqlin.marginals[n])


# ------------------------------------------------ global and local (add-on c)
LOCAL = dict(R_G=400.0,
             providers=[dict(name="Mainland", region="mainland", mw=500.0, price=3.0),
                        dict(name="SA provider 1", region="SA", mw=40.0, price=10.0),
                        dict(name="SA provider 2", region="SA", mw=60.0, price=50.0)])


def global_local(R_SA, R_G=None):
    R_G = LOCAL["R_G"] if R_G is None else R_G
    pr = LOCAL["providers"]
    c = [q["price"] for q in pr]
    A_ub = [[-1.0] * len(pr), [-(1.0 if q["region"] == "SA" else 0.0) for q in pr]]
    res = linprog(c, A_ub=A_ub, b_ub=[-R_G, -R_SA], bounds=[(0, q["mw"]) for q in pr], method="highs")
    if res.status != 0: return None
    piG, piSA = -res.ineqlin.marginals[0], -res.ineqlin.marginals[1]
    return dict(x=res.x, cost=res.fun, piG=piG, piSA=piSA, price_mainland=piG, price_SA=piG + piSA)


# ------------------------------------------------------------- trapezium mode
TRAP_PRESETS = {
    "forum": {
        "label": "Review forum Q4 unit: 400 MW gas unit",
        "P_range": (0.0, 400.0), "P_default": 350.0,
        "services": {   # (Emin, Blo, Bhi, Emax, A)
            "Fast raise": (100, 160, 300, 400, 80),
            "Slow raise": (100, 160, 280, 400, 120),
            "Delayed raise": (100, 100, 250, 400, 150),
            "Regulation raise": (100, 120, 360, 400, 40),
            "Fast lower": (100, 200, 400, 400, 80),
            "Slow lower": (100, 220, 400, 400, 120),
            "Delayed lower": (100, 250, 400, 400, 150),
            "Regulation lower": (100, 140, 400, 400, 40),
        },
    },
    "lecture": {
        "label": "Lecture example (Part IV slide 10)",
        "P_range": (150.0, 520.0), "P_default": 480.0,
        "services": {"Fast raise": (200, 250, 450, 500, 100),
                     "Regulation raise": (200, 200, 470, 500, 30)},
    },
    "battery": {
        "label": "Battery: 100 MW, one bidirectional unit",
        "P_range": (-100.0, 100.0), "P_default": -60.0,
        "services": {
            "Very fast raise": (-100, -100, 0, 100, 100),
            "Fast raise": (-100, -100, 0, 100, 100),
            "Slow raise": (-100, -100, 0, 100, 100),
            "Delayed raise": (-100, -100, 0, 100, 100),
            "Regulation raise": (-100, -100, 50, 100, 50),
            "Very fast lower": (-100, 0, 100, 100, 100),
            "Fast lower": (-100, 0, 100, 100, 100),
            "Slow lower": (-100, 0, 100, 100, 100),
            "Delayed lower": (-100, 0, 100, 100, 100),
            "Regulation lower": (-100, -50, 100, 100, 50),
        },
    },
}


def slopes(t):
    Emin, Blo, Bhi, Emax, A = t
    return (Emax - Bhi) / A, (Blo - Emin) / A          # US, LS


def availability(t, P, g_raise=0.0, g_lower=0.0, service=""):
    """FCAS a unit can be enabled for at energy target P, with the joint rows of
    Part IV slide 8 for contingency services (regulation adds with coefficient 1)."""
    Emin, Blo, Bhi, Emax, A = t
    US, LS = slopes(t)
    if P < Emin - 1e-9 or P > Emax + 1e-9:
        return 0.0, "outside enablement range"
    is_contingency = "Regulation" not in service
    gr = g_raise if (is_contingency and "raise" in service) else 0.0
    gl = g_lower if (is_contingency and "lower" in service) else 0.0
    cands = {"flat top": A}
    if US > 0: cands["right row"] = (Emax - P - gr) / US
    if LS > 0: cands["left row"] = (P - gl - Emin) / LS
    side = min(cands, key=cands.get)
    return max(0.0, cands[side]), side


# ======================================================================
# Pure helpers (no Streamlit calls from here down to the charts)
# ======================================================================

def _z(x) -> float:
    """HiGHS round-off and -0.0 off a number students read."""
    x = float(x)
    return 0.0 if abs(x) < 1e-9 else x


def unique(rng, tol: float = 1e-6) -> bool:
    """True when the left and right changes in cost agree."""
    lo, hi = rng
    return lo is not None and hi is not None and abs(lo - hi) <= tol


def _cost(z):
    return None if z is None else z["cost"]


def _plain(x):
    """Numpy out, plain floats and lists in, so cached results pickle cleanly."""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_plain(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return _z(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _unit_label(u: dict) -> str:
    return f"{u['name']} ({u['tech']})"


# --- Raise: sequential methods ------------------------------------------

def energy_step_lam_range(preset: str):
    """Left and right energy price in the energy-only first step of energy first."""
    p = RAISE_PRESETS[preset]
    units, D = p["units"], p["D"]
    return _range(lambda d: _cost(_raise_lp(units, d, 0.0, 0.0)), D)


def ef_headroom(preset: str, batt: float = 0.0) -> float:
    """MW of raise left after the energy-only dispatch: sum of min(RR, Pbar - P), plus the battery."""
    p = RAISE_PRESETS[preset]
    units = p["units"]
    e = _raise_lp(units, p["D"], 0.0, 0.0)
    return float(sum(min(u["RR"], u["Pmax"] - e["P"][k]) for k, u in enumerate(units)) + batt)


def _reserve_only(preset: str, R: float, batt: float = 0.0):
    """Step 1 of reserve first: buy reserve alone, from each unit's room above its minimum."""
    units = RAISE_PRESETS[preset]["units"]
    n = len(units)
    c = [u["cp"] for u in units] + [BATTERY_RAISE_OFFER]
    bounds = [(0.0, min(u["RR"], u["Pmax"] - u["Pmin"])) for u in units] + [(0.0, batt)]
    res = linprog(c, A_ub=[[-1.0] * (n + 1)], b_ub=[-R], bounds=bounds, method="highs")
    if res.status != 0:
        return None
    return dict(r=res.x, cost=res.fun, pi=-res.ineqlin.marginals[0])


def reserve_first_ranges(preset: str, R: float, batt: float = 0.0):
    """Price ranges of reserve first: the reserve step pi, and the energy step lambda."""
    p = RAISE_PRESETS[preset]
    units, D = p["units"], p["D"]
    rs = _reserve_only(preset, R, batt)
    if rs is None:
        return None
    pi_rng = _range(lambda r: _cost(_reserve_only(preset, r, batt)), R)
    held = list(rs["r"])
    lam_rng = _range(lambda d: _cost(_raise_lp(units, d, 0.0, 0.0, fix_r=held)), D)
    return dict(pi_range=pi_rng, lam_range=lam_rng)


def ef_full(preset: str, R: float, batt: float = 0.0) -> dict:
    """Energy first with its energy step range and the headroom it had."""
    res = energy_first(preset, R, batt)
    return dict(res=res, lam_range=energy_step_lam_range(preset),
                headroom=ef_headroom(preset, batt))


def rf_full(preset: str, R: float, batt: float = 0.0) -> dict:
    res = reserve_first(preset, R, batt)
    rng = reserve_first_ranges(preset, R, batt)
    return dict(res=res, pi_range=None if rng is None else rng["pi_range"],
                lam_range=None if rng is None else rng["lam_range"])


# --- Raise: supply curve --------------------------------------------------

def _push(out: list, lo: float, hi: float, *vals) -> None:
    """Append a segment, merging it into the last one when the values match."""
    if out and all(abs(a - b) < 1e-6 for a, b in zip(out[-1][2:], vals)):
        out[-1] = (out[-1][0], hi) + tuple(out[-1][2:])
    else:
        out.append((lo, hi) + tuple(vals))


def price_steps(preset: str, batt: float = 0.0) -> list:
    """(R_from, R_to, pi, lambda) segments, solved at half-MW midpoints so every riser
    sits exactly on its breakpoint (the raw sweep picks a side at a breakpoint)."""
    p = RAISE_PRESETS[preset]
    out: list = []
    R = 0.5
    while R < p["R_max"]:
        s = _raise_lp(p["units"], p["D"], R, batt)
        if s is None:
            break
        _push(out, R - 0.5, R + 0.5, _z(round(s["pi"], 6)), _z(round(s["lam"], 6)))
        R += 1.0
    return out


def offer_stack(preset: str, batt: float = 0.0) -> list:
    """(name, MW, offer) in merit order: the battery first when present, then by c+."""
    units = RAISE_PRESETS[preset]["units"]
    out = []
    if batt > 0:
        out.append(("Battery", float(batt), BATTERY_RAISE_OFFER))
    out += sorted(((u["name"], u["RR"], u["cp"]) for u in units), key=lambda t: t[2])
    return out


# --- Raise: who sets the price --------------------------------------------

def lam_setter(preset: str, s: dict, batt: float = 0.0):
    """One sentence on what sets lambda, or None when no rule matches."""
    units = RAISE_PRESETS[preset]["units"]
    for k, u in enumerate(units):
        if s["P"][k] > u["Pmin"] + EPS and u["Pmax"] - s["P"][k] - s["r"][k] > EPS:
            return f"set by {u['name']}'s energy offer"
    for k, u in enumerate(units):
        if EPS < s["r"][k] < u["RR"] - EPS:
            return (f"set by {u['name']}: its energy offer plus the reserve margin it "
                    "would give up")
    return None


def pi_setter(preset: str, s: dict, batt: float = 0.0):
    """One sentence on what sets pi+, or None when no rule matches. Uses LaTeX."""
    units = RAISE_PRESETS[preset]["units"]
    for k, u in enumerate(units):
        if EPS < s["r"][k] < u["RR"] - EPS:
            nm = u["name"]
            if u["Pmax"] - s["P"][k] - s["r"][k] > EPS:
                return f"set by {nm}'s reserve offer: {nm} has spare headroom"
            return (rf"set by {nm}: offer $c^{{+}}_{{{nm}}}$ plus the energy margin it gives up, "
                    rf"$\lambda - c_{{{nm}}}$: {_n(u['cp'])} + ({_n(s['lam'])} − {_n(u['c'])}) "
                    f"= {_n(s['pi'])}")
    if batt > 0 and EPS < s["rB"] < batt - EPS:
        return "set by the battery's offer"
    return None


def verdicts(preset: str, s: dict, batt: float, pi_unique: bool) -> list:
    """(name, offer, margin, total, verdict) per unit, and the battery last when present.
    Verdicts rest on quantities; the 'above the price' clause needs a unique price."""
    units = RAISE_PRESETS[preset]["units"]
    out = []
    for k, u in enumerate(units):
        r = s["r"][k]
        if r >= u["RR"] - EPS:
            v = f"holds all it can (RR<sub>{u['name']}</sub> binds)"
        elif r > EPS:
            v = "holds reserve; its full cost equals the price" if pi_unique else "holds reserve"
        else:
            v = "holds none: its full cost is above the price" if pi_unique else "holds none"
        out.append((u["name"], u["cp"], s["mubar"][k], s["reserve_cost"][k], v))
    if batt > 0:
        r = s["rB"]
        if r >= batt - EPS:
            v = "holds all it offers"
        elif r > EPS:
            v = "holds reserve; its full cost equals the price" if pi_unique else "holds reserve"
        else:
            v = "holds none: its full cost is above the price" if pi_unique else "holds none"
        out.append(("Battery", BATTERY_RAISE_OFFER, 0.0, BATTERY_RAISE_OFFER, v))
    return out


def settlement(preset: str, s: dict, R: float, batt: float = 0.0) -> dict:
    """Margins per unit in $/h, what consumers pay, the reserve bill and the check lines."""
    p = RAISE_PRESETS[preset]
    units, D = p["units"], p["D"]
    lam, pi = s["lam"], s["pi"]
    rows, checks = [], []
    for k, u in enumerate(units):
        em = (lam - u["c"]) * s["P"][k]
        rm = (pi - u["cp"]) * s["r"][k]
        rows.append(dict(name=u["name"], energy=em, reserve=rm, total=em + rm))
        if s["P"][k] > u["Pmin"] + EPS and EPS < s["r"][k] < u["RR"] - EPS:
            checks.append(dict(name=u["name"], e_margin=lam - u["c"], r_margin=pi - u["cp"],
                               lam=lam, c=u["c"], pi=pi, cp=u["cp"]))
    if batt > 0:
        rm = (pi - BATTERY_RAISE_OFFER) * s["rB"]
        rows.append(dict(name="Battery", energy=0.0, reserve=rm, total=rm))
    return dict(rows=rows, consumers=lam * D, bill=pi * R, checks=checks)


# --- Lower, global and local ------------------------------------------------

def lower_ranges(preset: str, Rm: float) -> dict:
    D = LOWER_PRESETS[preset]["D"]
    return dict(lam_range=_range(lambda d: _cost(lower_lp(preset, Rm, D=d)), D),
                pi_range=_range(lambda r: _cost(lower_lp(preset, r)), Rm))


def lower_setter(preset: str, s: dict):
    """(unit, c-, c, lambda, pi-) for the unit holding lower strictly inside its limits."""
    for k, u in enumerate(LOWER_PRESETS[preset]["units"]):
        if u["cm"] > 0 and EPS < s["r"][k] < u["RRlow"] - EPS:
            return dict(name=u["name"], cm=u["cm"], c=u["c"], lam=s["lam"], pi=s["pi"])
    return None


def lower_steps(preset: str) -> list:
    """(Rm_from, Rm_to, pi-, lambda) segments from half-MW midpoint solves."""
    p = LOWER_PRESETS[preset]
    out: list = []
    R = 0.5
    while R < p["R_max"]:
        s = lower_lp(preset, R)
        if s is None:
            break
        _push(out, R - 0.5, R + 0.5, _z(round(s["pi"], 6)), _z(round(s["lam"], 6)))
        R += 1.0
    return out


def _gl_cost(R_SA: float, R_G: float | None = None):
    z = global_local(R_SA, R_G)
    return None if z is None else z["cost"]


def gl_ranges(R_SA: float) -> dict:
    """Price ranges of the global row, the South Australian row, and the SA regional price."""
    pg = _range(lambda g: _gl_cost(R_SA, g), LOCAL["R_G"])
    ps = _range(lambda r: _gl_cost(r), R_SA)
    sa = tuple(None if (a is None or b is None) else a + b for a, b in zip(pg, ps))
    return dict(piG_range=pg, piSA_range=ps, sa_range=sa)


def sa_stack_price(R_SA: float) -> float:
    """Offer of the South Australian provider that serves the last MW of R_SA."""
    sa = sorted((q for q in LOCAL["providers"] if q["region"] == "SA"), key=lambda q: q["price"])
    cum = 0.0
    for q in sa:
        cum += q["mw"]
        if R_SA <= cum + 1e-9:
            return q["price"]
    return sa[-1]["price"]


# --- Trapeziums ---------------------------------------------------------------

def effective_g(service: str, g_raise: float, g_lower: float) -> tuple:
    """The regulation each service sees: contingency services only, own direction only."""
    cont = "Regulation" not in service
    return (g_raise if cont and "raise" in service else 0.0,
            g_lower if cont and "lower" in service else 0.0)


def reg_cap(preset: str, P: float, kind: str) -> float:
    """What the regulation trapezium itself allows at energy target P. kind is raise or lower."""
    name = f"Regulation {kind}"
    t = TRAP_PRESETS[preset]["services"].get(name)
    if t is None:
        return 0.0
    return float(availability(t, P, service=name)[0])


def trap_steps(t, P: float, g_raise: float, g_lower: float, service: str) -> list:
    """The three rows with the numbers substituted: dicts of row, label, tex, value."""
    Emin, Blo, Bhi, Emax, A = t
    US, LS = slopes(t)
    gr, gl = effective_g(service, g_raise, g_lower)
    steps = [dict(row="flat top", label="flat top", tex=rf"A_k = {_m(A)}", value=float(A))]
    if US > 0:
        val = (Emax - P - gr) / US
        sym = r" - g^{+}_k" if gr > 0 else ""
        num = f" - {_m(gr)}" if gr > 0 else ""
        steps.append(dict(row="right row", label="right row", value=val,
                          tex=rf"(E^{{max}}_k - P_k{sym}) / US_k = ({_m(Emax)} - {_p(P)}{num}) "
                              rf"/ {_m(US)} = {_mw(val)}"))
    else:
        steps.append(dict(row="right row", label="right row", tex="", value=None))
    if LS > 0:
        val = (P - gl - Emin) / LS
        sym = r" - g^{-}_k" if gl > 0 else ""
        num = f" - {_m(gl)}" if gl > 0 else ""
        steps.append(dict(row="left row", label="left row", value=val,
                          tex=rf"(P_k{sym} - E^{{min}}_k) / LS_k = ({_p(P)}{num} - {_p(Emin)}) "
                              rf"/ {_m(LS)} = {_mw(val)}"))
    else:
        steps.append(dict(row="left row", label="left row", tex="", value=None))
    return steps


# --- Formatting ---------------------------------------------------------------

def _n(x: float) -> str:
    """Two decimals, no trailing .00 on an integer, and a space between thousands."""
    s = f"{round(float(x), 2) + 0.0:,.2f}"
    s = s[:-3] if s.endswith(".00") else s
    return s.replace(",", " ")


def _m(x: float) -> str:
    """_n for maths: a thin space between thousands, which KaTeX renders."""
    return _n(x).replace(" ", r"\,")


def _p(x: float) -> str:
    """A negative number wrapped in brackets, for substituting into an expression."""
    return f"({_m(x)})" if round(x, 2) < 0 else _m(x)


def _sp(x: float) -> str:
    """A whole number with a space between thousands, as the lecture sentences write it."""
    return f"{x:,.0f}".replace(",", " ")


def _mw(x: float) -> str:
    """MW to one decimal, without a trailing .0."""
    s = f"{round(float(x), 1) + 0.0:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _pipe_table(head: list[str], rows: list[list[str]]) -> str:
    """A markdown table, so its cells reach KaTeX."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def nonunique_sentence(step: int = 10) -> str:
    return ("At exactly this requirement the solution changes from one case to the next "
            "(for example, a unit's spare headroom runs out), so the price is not unique. "
            f"Move the slider by {step} MW.")


def fmt_price(rng, beyond_text: str, step: int = 10) -> tuple:
    """(headline, sentence or None) for a price range under the range rule."""
    lo, hi = rng
    if unique(rng):
        return _n(lo), None
    if lo is not None and hi is not None:
        return f"between {_n(lo)} and {_n(hi)}", nonunique_sentence(step)
    if lo is not None:
        return f"{_n(lo)} or more", beyond_text
    if hi is not None:
        return f"up to {_n(hi)}", nonunique_sentence(step)
    return "none", beyond_text


def _beyond_pi(R: float) -> str:
    return (f"There is no feasible dispatch above {_sp(R)} MW, so the price has no "
            "right-hand value.")


BEYOND_LAM = ("There is no feasible dispatch with 1 MW more demand, so the price has no "
              "right-hand value.")


# --- Trail and method comparison (pure) -------------------------------------

TRAIL_CAP = 12
METHOD_SHORT = {"coopt": "Co-optimised", "ef": "Energy first", "rf": "Reserve first"}


def trail_push(trail: list, entry: dict, cap: int = TRAIL_CAP) -> list:
    """A new list. Skip the entry if the last run had the same knobs; otherwise number
    it (one more than the last run) and keep only the last `cap` runs."""
    if trail and trail[-1]["knobs"] == entry["knobs"]:
        return trail
    n = trail[-1]["n"] + 1 if trail else 1
    return (list(trail) + [{**entry, "n": n}])[-cap:]


def trail_marks(points) -> list:
    """points: (n, x, y, hover, other). Points at the same rounded (x, y) are merged so
    their numbers read "2, 5". Runs on a different curve (`other`) are kept apart from runs
    on the same curve, so a circle and a square never merge. Returns (x, y, label, hover, other) groups."""
    groups: dict = {}
    for n, x, y, hover, other in points:
        g = groups.setdefault((round(float(x), 6), round(float(y), 6), bool(other)),
                              dict(x=float(x), y=float(y), ns=[], hover=[], other=bool(other)))
        g["ns"].append(n)
        g["hover"].append(hover)
    return [(g["x"], g["y"], ", ".join(str(n) for n in g["ns"]), "<br>".join(g["hover"]),
             g["other"]) for g in groups.values()]


def method_costs(preset: str, batt: float = 0.0, step: int = 10) -> list:
    """(R, co-optimised, energy first, reserve first) total cost in $/h along the
    requirement, with None where a method cannot meet it."""
    p = RAISE_PRESETS[preset]
    out = []
    for R in range(0, int(p["R_max"]) + 1, step):
        co = _raise_lp(p["units"], p["D"], float(R), float(batt))
        ef = energy_first(preset, float(R), float(batt))
        rf = reserve_first(preset, float(R), float(batt))
        out.append((float(R),
                    None if co is None else _z(co["cost"]),
                    _z(ef["cost"]) if ef is not None and ef["feasible"] else None,
                    _z(rf["cost"]) if rf is not None and rf["feasible"] else None))
    return out


def range_low(rng):
    """Where a marker for a price range is drawn: the low end, or the high end if none."""
    lo, hi = rng
    return hi if lo is None else lo


# ======================================================================
# Charts
# ======================================================================

METHODS = {
    "coopt": "Co-optimised (one LP)",
    "ef": "Energy first, then reserve",
    "rf": "Reserve first, then energy",
}
BATT_MAX = {"forum": 200, "lecture": 300}
RESERVE_FILL = ed.PURPLE


def _pattern(colour, shape, fg=ed.NAVY):
    return dict(color=colour, line=dict(color=ed.NAVY, width=1.5),
                pattern=dict(shape=shape, fgcolor=fg, bgcolor=colour, size=8))


def _reserve_marker():
    """Purple stripes on lavender, so numbers printed on the bar stay readable."""
    return dict(color=ed.LAVENDER, line=dict(color=ed.NAVY, width=1.5),
                pattern=dict(shape="/", fgcolor=ed.PURPLE, bgcolor=ed.LAVENDER, size=12,
                             solidity=0.25))


def _layout(fig, title, height=460, legend=True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=ed.NAVY)),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=14, color=ed.NAVY), orientation="h", y=-0.25),
        height=height, margin=dict(t=70, b=40, l=40, r=40), showlegend=legend,
        separators=". ",
    )


def _axes(fig, xtitle, ytitle, **kw):
    fig.update_xaxes(title=dict(text=xtitle, font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.SILVER, **kw)
    fig.update_yaxes(title=dict(text=ytitle, font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.NAVY)


def _step_xy(segments, vi: int):
    """x and y arrays that draw (lo, hi, ..., value) segments as a step line."""
    xs, ys = [], []
    for seg in segments:
        xs += [seg[0], seg[1]]
        ys += [seg[vi], seg[vi]]
    return xs, ys


def _vline(fig, x, colour, dash="dash", width=3, **kw):
    fig.add_vline(x=x, line=dict(color=colour, width=width, dash=dash), **kw)


def _layout_narrow(fig, title, height, legend=True, legend_y=1.02, top=100):
    """The layout for a chart in the right-hand column: a short title anchored top left,
    the legend between the title and the plot, tight margins, and text that hides rather
    than overflows. The top margin is the same whether or not a legend is showing, so a
    chart does not jump when the first earlier run appears."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color=ed.NAVY), x=0, xanchor="left",
                   y=0.99, yanchor="top"),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=13, color=ed.NAVY), orientation="h", y=legend_y,
                    yanchor="bottom", x=0),
        height=height, margin=dict(t=top, b=40, l=10, r=10),
        showlegend=legend, uniformtext=dict(minsize=11, mode="hide"), separators=". ",
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)


def _trail_pos(y, yrange) -> str:
    """Label below the marker, unless the marker is in the bottom tenth of the axis,
    where the label would collide with the tick labels."""
    if yrange is not None and yrange[1] > yrange[0] and (y - yrange[0]) / (yrange[1] - yrange[0]) < 0.1:
        return "top center"
    return "bottom center"


def _add_trail(fig, groups, row=None, col=None, legend=True, labels=True,
               other_name="earlier runs, other battery value", yrange=None) -> None:
    """Earlier runs as faded, numbered markers. Circles are runs on the same curve;
    squares (`other`) are runs on a different curve or shape. Neither is the current
    diamond, and the number carries the meaning, not the colour."""
    kw = dict(row=row, col=col) if row else {}
    for is_other, name, symbol in ((False, "earlier runs (number = run)", "circle"),
                                   (True, other_name, "square")):
        g = [t for t in groups if bool(t[4]) == is_other]
        if not g:
            continue
        fig.add_trace(go.Scatter(
            x=[t[0] for t in g], y=[t[1] for t in g],
            mode="markers+text" if labels else "markers", opacity=0.75, name=name,
            legendgroup="trail_other" if is_other else "trail", showlegend=legend,
            text=[t[2] for t in g] if labels else None,
            textposition=[_trail_pos(t[1], yrange) for t in g],
            textfont=dict(size=12, color=ed.MUTED), cliponaxis=False,
            hovertext=[t[3] for t in g], hoverinfo="text",
            marker=dict(size=11, symbol=symbol, color="#FFFFFF",
                        line=dict(color=ed.MUTED, width=2))), **kw)


def _dispatch_compare(preset, disp, batt, shown) -> go.Figure:
    """Energy and reserve for each unit under each ticked method, grouped by unit."""
    units = RAISE_PRESETS[preset]["units"]
    outer, inner, energy, res, spare = [], [], [], [], []
    for k, u in enumerate(units):
        label = _unit_label(u) + (f", min {_mw(u['Pmin'])} MW" if u["Pmin"] > 0 else "")
        for m in shown:
            z = disp.get(m)
            if z is None:
                continue
            outer.append(label)
            inner.append(METHOD_SHORT[m])
            energy.append(float(z["P"][k]))
            res.append(float(z["r"][k]))
            spare.append(max(0.0, u["Pmax"] - z["P"][k] - z["r"][k]))
    if batt > 0:
        for m in shown:
            z = disp.get(m)
            if z is None:
                continue
            outer.append("Battery (idle)")
            inner.append(METHOD_SHORT[m])
            energy.append(0.0)
            res.append(float(z["rB"]))
            spare.append(max(0.0, batt - z["rB"]))

    def lab(vals, prefix=""):
        return [f"{prefix}{_mw(v)}" if v > EPS else "" for v in vals]

    y = [outer, inner]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=y, x=energy, orientation="h", name="Energy P<sub>k</sub>",
                         marker=_pattern(ed.NAVY, ""), text=lab(energy), textposition="inside",
                         insidetextanchor="middle", textfont=dict(size=13, color="#FFFFFF")))
    fig.add_trace(go.Bar(y=y, x=res, orientation="h", name="Reserve r<sup>+</sup><sub>k</sub> (hatched)",
                         marker=_reserve_marker(), text=lab(res),
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=14, weight="bold", color=ed.NAVY), textangle=0))
    fig.add_trace(go.Bar(y=y, x=spare, orientation="h", name="Spare capacity",
                         marker=dict(color="#FFFFFF", line=dict(color=ed.NAVY, width=2)),
                         text=lab(spare, "spare "), textposition="inside",
                         insidetextanchor="middle", textfont=dict(size=12, color=ed.NAVY)))
    fig.update_layout(barmode="stack", bargap=0.25)
    fig.update_yaxes(autorange="reversed")
    _axes(fig, "capacity (MW)", "")
    _layout_narrow(fig, "Each MW of capacity is sold once: as energy or as reserve",
                   height=max(260, 150 + 34 * len(inner)))
    fig.update_layout(legend=dict(traceorder="normal"))
    return fig


METHOD_STYLE = {"coopt": (ed.NAVY, "solid", "circle"), "ef": (ed.PURPLE, "dash", "square"),
                "rf": (ed.MUTED, "dot", "triangle-up")}


def _cost_curves(preset, batt, R, shown, trail, mcosts, current) -> go.Figure:
    """Total cost against the requirement, one line per ticked method. Each line has its
    own dash and marker shape. Earlier runs (same battery value) sit on the lines."""
    fig = go.Figure()
    col = {"coopt": 1, "ef": 2, "rf": 3}
    for m in shown:
        colour, dash, symbol = METHOD_STYLE[m]
        fig.add_trace(go.Scatter(
            x=[t[0] for t in mcosts], y=[t[col[m]] for t in mcosts], mode="lines+markers",
            name=METHOD_SHORT[m], connectgaps=False,
            line=dict(color=colour, width=3, dash=dash),
            marker=dict(size=6, symbol=symbol, color=colour)))
    first = True
    vals = [t[col[m]] for t in mcosts for m in shown if t[col[m]] is not None]
    yr = (min(vals), max(vals)) if vals else None
    for m in shown:
        pts = [(e["n"], e["R"], e[m]["cost"],
                f"run {e['n']}: R⁺ {_sp(e['R'])} MW, {METHOD_SHORT[m]} {_sp(e[m]['cost'])} $/h", False)
               for e in trail[:-1] if e["batt"] == batt and e[m]["ok"]]
        if pts:
            _add_trail(fig, trail_marks(pts), legend=first, labels=first, yrange=yr)
            first = False
    _vline(fig, R, ed.PURPLE, annotation_text=f"R<sup>+</sup> = {_sp(R)} MW",
           annotation_position="top left" if R > 0.6 * RAISE_PRESETS[preset]["R_max"]
           else "top right", annotation_font=dict(size=14, color=ed.NAVY))
    for m in shown:
        if current.get(m) is None:
            continue
        fig.add_trace(go.Scatter(
            x=[R], y=[current[m]], mode="markers", showlegend=False, hoverinfo="skip",
            marker=dict(size=14, symbol="diamond", color="#FFFFFF", line=dict(color=ed.NAVY, width=3))))
    _axes(fig, "reserve requirement R<sup>+</sup> (MW)", "total cost ($/h)")
    fig.update_yaxes(tickformat=",")
    fig.update_xaxes(range=[0, RAISE_PRESETS[preset]["R_max"] * 1.02])
    _layout_narrow(fig, "Total cost against the requirement", height=380)
    return fig


def _full_cost_bars(rows, pi_rng) -> go.Figure:
    names = [r[0] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=names, x=[r[1] for r in rows], orientation="h",
                         name="Offer c<sup>+</sup><sub>k</sub>",
                         marker=dict(color=ed.SILVER, line=dict(color=ed.NAVY, width=1.5))))
    fig.add_trace(go.Bar(y=names, x=[r[2] for r in rows], orientation="h",
                         name="Energy margin given up μ̄<sub>k</sub> (hatched)",
                         marker=_pattern(RESERVE_FILL, "/", fg=ed.LAVENDER)))
    top = max(r[3] for r in rows)
    fig.add_trace(go.Scatter(
        x=[r[3] for r in rows], y=names, mode="text", showlegend=False, hoverinfo="skip",
        text=[f"<b>{_n(r[3])}</b>: {r[4]}" for r in rows], textposition="middle right",
        textfont=dict(size=14, color=ed.NAVY)))
    lo, hi = pi_rng
    if unique(pi_rng):
        marks = [(lo, f"reserve price {PI}<sup>+</sup> = {_n(lo)}")]
    else:
        marks = [(lo, f"reserve price range {_n(lo)}" + (f" to {_n(hi)}" if hi is not None else " or more"))]
        if hi is not None:
            marks.append((hi, ""))
    for x, text in marks:
        fig.add_shape(type="line", xref="x", yref="paper", x0=x, x1=x, y0=0, y1=1,
                      line=dict(color=ed.NAVY, width=3, dash="dash"))
        if text:
            fig.add_annotation(x=x, y=1.0, yref="paper", text=text, showarrow=False,
                               yanchor="bottom", font=dict(size=14, color=ed.NAVY))
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(autorange="reversed")
    _axes(fig, "full cost of a MW of reserve ($/MW/h)", "")
    fig.update_xaxes(range=[0, top * 2.9])
    _layout(fig, "Full cost of reserve: the offer plus the energy margin given up",
            height=140 + 80 * len(rows))
    return fig


def _supply_curve(preset, batt, R, steps, mark_pi, mark_lam, pi_text, lam_text,
                  trail=None) -> go.Figure:
    R_max = RAISE_PRESETS[preset]["R_max"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.2,
                        subplot_titles=(f"Reserve price {PI}<sup>+</sup> ($/MW/h)",
                                        f"Energy price {LAMBDA} ($/MWh)"))
    fig.update_annotations(font=dict(size=16, color=ed.NAVY))
    xs, ys = _step_xy(steps, 2)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"reserve price {PI}<sup>+</sup>",
                             line=dict(color=ed.NAVY, width=4)), row=1, col=1)
    stack, cum, sx, sy = offer_stack(preset, batt), 0.0, [], []
    for _, mw, price in stack:
        sx += [cum, cum + mw]
        sy += [price, price]
        cum += mw
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines", name="offers only",
                             line=dict(color=ed.PURPLE, width=3, dash="dot")), row=1, col=1)
    xs, ys = _step_xy(steps, 3)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"energy price {LAMBDA}",
                             line=dict(color=ed.NAVY, width=4)), row=2, col=1)
    top = max([s[2] for s in steps] + [p for _, _, p in stack] + [mark_pi]) * 1.3
    lam_top = max([s[3] for s in steps] + [mark_lam]) * 1.6
    if trail:
        _add_trail(fig, trail["pi"], 1, 1, yrange=(0, top))
        _add_trail(fig, trail["lam"], 2, 1, legend=False, yrange=(0, lam_top))
    left = R > 0.6 * R_max
    for row, y, text in ((1, mark_pi, pi_text), (2, mark_lam, lam_text)):
        _vline(fig, R, ed.PURPLE, row=row, col=1)
        fig.add_trace(go.Scatter(
            x=[R], y=[y], mode="markers", showlegend=False, hoverinfo="skip",
            marker=dict(size=15, symbol="diamond", color="#FFFFFF",
                        line=dict(color=ed.NAVY, width=3))), row=row, col=1)
        # No background box: it would hide a step line and fake a gap in the curve.
        fig.add_annotation(x=R, y=y, text=text, showarrow=False, row=row, col=1,
                           xanchor="right" if left else "left", xshift=-14 if left else 14,
                           yanchor="bottom", yshift=20,
                           font=dict(size=14, color=ed.NAVY))
    fig.update_xaxes(tickfont=ed.TICK_FONT, gridcolor=ed.SILVER, range=[0, R_max * 1.02])
    fig.update_xaxes(title=dict(text="reserve requirement R<sup>+</sup> (MW)", font=ed.CHART_FONT),
                     row=2, col=1)
    fig.update_yaxes(tickfont=ed.TICK_FONT, gridcolor=ed.SILVER, rangemode="tozero")
    fig.update_yaxes(range=[0, top], row=1, col=1)
    fig.update_yaxes(range=[0, lam_top], row=2, col=1)
    _layout_narrow(fig, "The reserve supply curve and the energy price", height=520,
                   legend_y=1.12, top=120)
    return fig


def _trap_points(t):
    Emin, Blo, Bhi, Emax, A = t
    return [Emin, Blo, Bhi, Emax, Emin], [0, A, A, 0, 0]


def _tick_labels(values: list, names: list):
    """Plotly ticks at the given positions; names that share a position are joined."""
    grouped: dict = {}
    for v, n in zip(values, names):
        grouped.setdefault(v, []).append(n)
    return list(grouped), [f"{', '.join(ns)} = {_mw(v)}" for v, ns in grouped.items()]


def _trapezium(t, P, gr, gl, service, avail, side, xrange, trail=None) -> go.Figure:
    Emin, Blo, Bhi, Emax, A = t
    US, LS = slopes(t)
    g_r, g_l = effective_g(service, gr, gl)
    fig = go.Figure()
    xs, ys = _trap_points(t)
    fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", fillcolor=ed.LAVENDER, mode="lines",
                             line=dict(color=ed.NAVY, width=3), hoverinfo="skip",
                             name="enablement trapezium"))
    rows = {"flat top": ((Blo, A), (Bhi, A)), "right row": ((Bhi, A), (Emax, 0)),
            "left row": ((Emin, 0), (Blo, A))}
    shifted = {}
    if g_r > 0 and US > 0:
        shifted["right row"] = ((Bhi - g_r, A), (Emax - g_r, 0))
    if g_l > 0 and LS > 0:
        shifted["left row"] = ((Emin + g_l, 0), (Blo + g_l, A))
    shape_names = {"flat top": "flat top: r<sub>k</sub> ≤ A<sub>k</sub>",
                   "right row": "right row", "left row": "left row"}
    offsets = {"flat top": dict(yshift=16, xanchor="center"),
               "right row": dict(xshift=12, xanchor="left"),
               "left row": dict(xshift=-12, xanchor="right")}
    binding = side if side in rows else None
    for name, ((x0, y0), (x1, y1)) in rows.items():
        sym = "g<sup>+</sup>" if name == "right row" else "g<sup>-</sup>"
        text = shape_names[name]
        if name in shifted:
            (sx0, sy0), (sx1, sy1) = shifted[name]
            fig.add_trace(go.Scatter(x=[sx0, sx1], y=[sy0, sy1], mode="lines", showlegend=False,
                                     hoverinfo="skip", line=dict(color=ed.PURPLE, width=3, dash="dash")))
            gv = g_r if name == "right row" else g_l
            fig.add_annotation(x=(sx0 + sx1) / 2, y=(sy0 + sy1) / 2, showarrow=False,
                               text=f"moved in by {sym} = {_mw(gv)} MW", xanchor="right",
                               xshift=-10, font=dict(size=14, color=ed.NAVY))
        if name == binding:
            (bx0, by0), (bx1, by1) = shifted.get(name, rows[name])
            fig.add_trace(go.Scatter(x=[bx0, bx1], y=[by0, by1], mode="lines", showlegend=False,
                                     hoverinfo="skip", line=dict(color=ed.PURPLE, width=7)))
            text += " <b>binds</b>"
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, showarrow=False, text=text,
                           font=dict(size=14, color=ed.NAVY),
                           **(dict(bordercolor=ed.PURPLE, borderwidth=2, bgcolor=ed.LIMESTONE)
                              if name == binding else {}), **offsets[name])
    fig.add_shape(type="line", xref="x", yref="paper", x0=P, x1=P, y0=0, y1=1,
                  line=dict(color=ed.NAVY, width=2, dash="dashdot"))
    mid = (Emin + Emax) / 2
    fig.add_annotation(x=P, y=0.98, yref="paper", text=f"energy target P<sub>k</sub> = {_mw(P)} MW",
                       showarrow=False, yanchor="top", xanchor="left" if P < mid else "right",
                       xshift=6 if P < mid else -6, font=dict(size=14, color=ed.NAVY))
    if trail:
        _add_trail(fig, trail, other_name="earlier runs, other regulation",
                   yrange=(-0.04 * A, A * 1.4))
    fig.add_trace(go.Scatter(
        x=[P], y=[avail], mode="markers+text", showlegend=False, hoverinfo="skip",
        text=[f"available: {_mw(avail)} MW"],
        textposition=("top " if avail < 0.15 * A else "bottom ") + ("right" if P < mid else "left"),
        textfont=dict(size=16, color=ed.NAVY),
        marker=dict(size=16, symbol="diamond", color="#FFFFFF", line=dict(color=ed.NAVY, width=3))))
    tv, tt = _tick_labels([Emin, Blo, Bhi, Emax], ["E<sup>min</sup>", "B<sup>lo</sup>", "B<sup>hi</sup>", "E<sup>max</sup>"])
    _axes(fig, "energy target (MW)", "FCAS (MW)")
    pad = 0.15 * (xrange[1] - xrange[0])
    fig.update_xaxes(tickvals=tv, ticktext=tt, range=[xrange[0] - pad, xrange[1] + pad])
    fig.update_yaxes(tickvals=[0, A], ticktext=["0", f"A = {_mw(A)}"], range=[-0.04 * A, A * 1.4])
    _layout_narrow(fig, f"{service}: the trapezium", height=460)
    return fig


def _trap_multiples(preset, P, gr, gl) -> go.Figure:
    services = TRAP_PRESETS[preset]["services"]
    raises = [s for s in services if "raise" in s]
    lowers = [s for s in services if "lower" in s]
    cols = max(len(raises), len(lowers))
    grid = [raises] + ([lowers] if lowers else [])
    titles = []
    for line in grid:
        for c in range(cols):
            if c < len(line):
                a = availability(services[line[c]], P, *effective_g(line[c], gr, gl), service=line[c])[0]
                titles.append(f"{line[c]}<br>{_mw(a)} MW")
            else:
                titles.append("")
    fig = make_subplots(rows=len(grid), cols=cols, subplot_titles=titles,
                        horizontal_spacing=0.05, vertical_spacing=0.2)
    fig.update_annotations(font=dict(size=14, color=ed.NAVY))
    for r, line in enumerate(grid, start=1):
        for c, name in enumerate(line, start=1):
            t = services[name]
            g_r, g_l = effective_g(name, gr, gl)
            a = availability(t, P, g_r, g_l, name)[0]
            xs, ys = _trap_points(t)
            fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", fillcolor=ed.LAVENDER, mode="lines",
                                     line=dict(color=ed.NAVY, width=2), hoverinfo="skip",
                                     showlegend=False), row=r, col=c)
            _vline(fig, P, ed.PURPLE, dash="dashdot", width=2, row=r, col=c)
            fig.add_trace(go.Scatter(x=[P], y=[a], mode="markers", showlegend=False, hoverinfo="skip",
                                     marker=dict(size=11, symbol="diamond", color="#FFFFFF",
                                                 line=dict(color=ed.NAVY, width=2.5))), row=r, col=c)
    fig.update_xaxes(tickfont=dict(size=12, color=ed.NAVY), gridcolor=ed.SILVER, nticks=4)
    fig.update_yaxes(tickfont=dict(size=12, color=ed.NAVY), gridcolor=ed.SILVER, rangemode="tozero")
    fig.update_layout(font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                      height=250 * len(grid) + 90, margin=dict(t=70, b=30, l=40, r=20),
                      separators=". ")
    return fig


def _lower_bars(preset, s) -> go.Figure:
    units = LOWER_PRESETS[preset]["units"]
    names = [u["name"] for u in units]
    P = [float(v) for v in s["P"]]
    mins = [u["Pmin"] for u in units]
    room = [P[k] - mins[k] for k in range(len(units))]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=names, x=mins, orientation="h", name="Minimum output",
                         marker=dict(color=ed.SILVER, line=dict(color=ed.NAVY, width=1.5)),
                         text=[f"min {_mw(v)} MW" if v > EPS else "" for v in mins],
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=14, color=ed.NAVY)))
    fig.add_trace(go.Bar(y=names, x=room, orientation="h", name="Lower room P<sub>k</sub> − min (hatched)",
                         marker=_reserve_marker(),
                         text=[f"{_mw(v)} MW" if v > EPS else "" for v in room],
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=14, color=ed.NAVY)))
    fig.add_trace(go.Scatter(
        x=P, y=names, mode="text", showlegend=False, hoverinfo="skip", textposition="middle right",
        text=[f"output {_mw(P[k])} MW, lower enabled {_mw(s['r'][k])} MW" for k in range(len(units))],
        textfont=dict(size=14, color=ed.NAVY)))
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(autorange="reversed")
    _axes(fig, "output (MW)", "")
    fig.update_xaxes(range=[0, max(P) * 2.3])
    _layout_narrow(fig, "Each unit: its minimum, its output and the lower room",
                   height=170 + 80 * len(units))
    return fig


def _lower_steps(steps, Rm, mark_pi, text, trail=None) -> go.Figure:
    xs, ys = _step_xy(steps, 2)
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", name=f"lower price {PI}<sup>−</sup>",
                               line=dict(color=ed.NAVY, width=4)))
    _vline(fig, Rm, ed.PURPLE)
    top = max(ys + [mark_pi]) * 1.3
    if trail:
        _add_trail(fig, trail, yrange=(0, top))
    fig.add_trace(go.Scatter(
        x=[Rm], y=[mark_pi], mode="markers+text", showlegend=False, hoverinfo="skip",
        text=[text], textposition="top left" if Rm > 0.6 * steps[-1][1] else "top right",
        textfont=dict(size=15, color=ed.NAVY),
        marker=dict(size=15, symbol="diamond", color="#FFFFFF", line=dict(color=ed.NAVY, width=3))))
    _axes(fig, "lower requirement R<sup>−</sup> (MW)", f"{PI}<sup>−</sup> ($/MW/h)")
    fig.update_yaxes(range=[0, top])
    _layout_narrow(fig, f"The lower price {PI}<sup>−</sup> against the requirement", height=400)
    return fig


def _sa_curve(R_SA, piG, piSA_text, trail=None) -> go.Figure:
    sa = sorted((q for q in LOCAL["providers"] if q["region"] == "SA"), key=lambda q: q["price"])
    xs, ys, cum = [0.0], [sa[0]["price"]], 0.0
    for q in sa:
        xs += [cum, cum + q["mw"]]
        ys += [q["price"], q["price"]]
        cum += q["mw"]
    xs, ys = xs[1:], ys[1:]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", name="South Australian offers",
                               line=dict(color=ed.NAVY, width=4, shape="linear")))
    _vline(fig, R_SA, ed.PURPLE)
    fig.add_hline(y=piG, line=dict(color=ed.NAVY, width=3, dash="dash"))
    fig.add_annotation(x=cum, y=piG, xanchor="right", yanchor="bottom", showarrow=False,
                       text=f"global price {PI}<sup>G</sup> = {_n(piG)}", font=dict(size=14, color=ed.NAVY))
    if trail:
        _add_trail(fig, trail, yrange=(0, max(ys) * 1.3))
    fig.add_trace(go.Scatter(
        x=[R_SA], y=[sa_stack_price(R_SA)], mode="markers+text", showlegend=False, hoverinfo="skip",
        text=[f"R<sup>SA</sup> = {_mw(R_SA)} MW"], textposition="top left" if R_SA > 60 else "top right",
        textfont=dict(size=15, color=ed.NAVY),
        marker=dict(size=15, symbol="diamond", color="#FFFFFF", line=dict(color=ed.NAVY, width=3))))
    _axes(fig, "South Australian local requirement R<sup>SA</sup> (MW)", "offer ($/MW/h)")
    fig.update_xaxes(range=[0, cum * 1.05])
    fig.update_yaxes(range=[0, max(ys) * 1.3])
    _layout_narrow(fig, "South Australia's local supply curve", height=420)
    return fig


# ======================================================================
# Cached wrappers: the arguments are the cache key
# ======================================================================

@st.cache_data(show_spinner=False)
def _coopt(preset: str, R: int, batt: int):
    return _plain(cooptimise(preset, float(R), float(batt)))


@st.cache_data(show_spinner=False)
def _ef(preset: str, R: int, batt: int):
    return _plain(ef_full(preset, float(R), float(batt)))


@st.cache_data(show_spinner=False)
def _rf(preset: str, R: int, batt: int):
    return _plain(rf_full(preset, float(R), float(batt)))


@st.cache_data(show_spinner=False)
def _mcosts(preset: str, batt: int):
    return method_costs(preset, float(batt))


@st.cache_data(show_spinner=False)
def _steps(preset: str, batt: int):
    return price_steps(preset, float(batt))


@st.cache_data(show_spinner=False)
def _lower(preset: str, Rm: int):
    s = _plain(lower_lp(preset, float(Rm)))
    if s is None:
        return None
    s.update(_plain(lower_ranges(preset, float(Rm))))
    return s


@st.cache_data(show_spinner=False)
def _lsteps(preset: str):
    return lower_steps(preset)


@st.cache_data(show_spinner=False)
def _gl(R_SA: int):
    s = _plain(global_local(float(R_SA)))
    if s is None:
        return None
    s.update(_plain(gl_ranges(float(R_SA))))
    return s


# ======================================================================
# The page
# ======================================================================

MODES = ("Co-optimise energy and raise", "FCAS trapeziums", "Lower services",
         "Global and local requirements")
MODE_SENTENCES = {
    MODES[0]: "Energy and contingency raise share each unit's capacity, so the reserve price "
              "includes the energy margin a unit gives up, and a reserve requirement can move "
              "the energy price.",
    MODES[1]: "How much of each FCAS service a unit can be enabled for at a given energy "
              "target, and how regulation shares the headroom with contingency services.",
    MODES[2]: "For lower services the opportunity cost flips sign: lower FCAS is expensive "
              "exactly when energy is cheap.",
    MODES[3]: "A regional FCAS price is the sum of the multipliers of every requirement row "
              "that covers the region.",
}
DEFAULTS = {"fc_mode": MODES[0]}


def _save(key: str) -> None:
    st.session_state["fc_keep_" + key[3:]] = st.session_state[key]


def _cb(key: str, then) -> None:
    _save(key)
    if then is not None:
        then()


def _kept(key: str, default, lo=None, hi=None, then=None, options=None) -> dict:
    """Widget kwargs for a widget drawn only inside one mode. Streamlit drops a widget's
    state when it is not drawn, so the value is kept under a shadow key and written back
    into the widget key just before the widget is drawn, clamped to the current range."""
    value = st.session_state.get("fc_keep_" + key[3:], default)
    if options is not None and value not in options:
        value = default
    if lo is not None:
        value = int(min(hi, max(lo, value)))
    st.session_state[key] = value
    return dict(key=key, on_change=_cb, args=(key, then))


def _put(key: str, value) -> None:
    """Set a widget's value and its shadow together (used when a preset changes)."""
    st.session_state[key] = value
    st.session_state["fc_keep_" + key[3:]] = value


def _reset_raise() -> None:
    p = RAISE_PRESETS[st.session_state["fc_raise_preset"]]
    _put("fc_R", int(p["R_default"]))
    _put("fc_batt", 0)


def _reset_trap() -> None:
    p = TRAP_PRESETS[st.session_state["fc_trap_unit"]]
    _put("fc_service", "Fast raise")
    _put("fc_P", int(p["P_default"]))
    _put("fc_g_raise", 0)
    _put("fc_g_lower", 0)


def _reset_lower() -> None:
    _put("fc_Rm", int(LOWER_PRESETS[st.session_state["fc_lower_preset"]]["R_default"]))


def _css() -> None:
    st.markdown(
        f"""<style>
[data-testid="stMarkdownContainer"] table {{ width: 100%; border-collapse: collapse; }}
[data-testid="stMarkdownContainer"] th, [data-testid="stMarkdownContainer"] td {{
  text-align: center; padding: .45rem .5rem; border-bottom: 1px solid {ed.SILVER};
}}
[data-testid="stMarkdownContainer"] th {{ border-bottom: 2px solid {ed.SILVER}; }}
</style>""", unsafe_allow_html=True)


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header("Energy and FCAS co-optimisation", "Topic 9: one capacity, two products")
    _css()
    mode = st.radio("Mode", MODES, horizontal=True, key="fc_mode")
    st.markdown(MODE_SENTENCES[mode])
    if mode == MODES[0]:
        _raise_page()
    elif mode == MODES[1]:
        _trap_page()
    elif mode == MODES[2]:
        _lower_page()
    else:
        _gl_page()


def _price_block(rng, beyond, step=10):
    """The headline string and the sentence under it for a price range."""
    return fmt_price(rng, beyond, step)


def _show_price(label, rng, beyond, setter):
    head, sentence = _price_block(rng, beyond)
    ed.headline(label, head)
    if sentence is not None:
        st.markdown(sentence)
    elif setter:
        st.markdown(setter)




# --- The trail: every knob change is recorded, earlier runs stay visible -------

def _trail(name: str, ctx, entry: dict) -> list:
    """Record this run and return the trail. The trail restarts when the context (the
    preset or unit, which changes the data) changes. These are plain session keys, not
    widget keys, so they survive a mode switch. The lists are created here, not in
    DEFAULTS, so no two sessions share one."""
    ss = st.session_state
    tk, ck = f"fc_trail_{name}", f"fc_trail_{name}_ctx"
    if ss.get(ck) != ctx:
        ss[tk] = []
        ss[ck] = ctx
    ss[tk] = trail_push(ss.get(tk, []), entry)
    return ss[tk]


def _clear_trail(name: str) -> None:
    st.session_state[f"fc_trail_{name}"] = []


def _clear_button(name: str, trail: list) -> None:
    st.button("Clear history", key=f"fc_clear_{name}", on_click=_clear_trail, args=(name,))
    st.caption(f"Run {trail[-1]['n']} recorded; the last {TRAIL_CAP} runs are kept.")


def _runs_table(head: list, rows: list) -> None:
    """The runs so far, oldest first, with the current (last) run in bold."""
    body = [[f"**{c}**" for c in r] if i == len(rows) - 1 else r for i, r in enumerate(rows)]
    st.markdown(_pipe_table(head, body))


# --- Mode 1 -----------------------------------------------------------------

def _raise_page() -> None:
    ss = st.session_state
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.radio("Preset", list(RAISE_PRESETS), horizontal=False,
                 format_func=lambda k: RAISE_PRESETS[k]["label"],
                 **_kept("fc_raise_preset", "forum", options=list(RAISE_PRESETS),
                         then=_reset_raise))
        preset = ss["fc_raise_preset"]
        p = RAISE_PRESETS[preset]
        R = int(st.slider(r"Contingency raise requirement $R^{+}$ (MW)", 0, int(p["R_max"]),
                          step=10, **_kept("fc_R", int(p["R_default"]), 0, int(p["R_max"]))))
        bmax = BATT_MAX[preset]
        batt = int(st.slider(r"Idle battery offering raise at 1 \$/MW/h (MW of raise)", 0, bmax,
                             step=50, **_kept("fc_batt", 0, 0, bmax)))
        st.caption("An idle battery's headroom displaces no energy sale, so its reserve costs "
                   "only its offer.")

    units, D = p["units"], p["D"]
    co = _coopt(preset, R, batt)
    if co is None:
        with right:
            ed.note(f"**No feasible dispatch.** The requirement of {_sp(R)} MW cannot be met.")
        return
    ef = _ef(preset, R, batt)
    rf = _rf(preset, R, batt)
    ef_ok = ef["res"] is not None and ef["res"]["feasible"]
    rf_ok = rf["res"] is not None and rf["res"]["feasible"]
    ef_msg = (f"**Energy first cannot meet the requirement.** Energy first cannot find {_sp(R)} MW "
              f"of raise in the headroom left after the energy market (only {_sp(ef['headroom'])} "
              "MW is left).")
    rf_msg = ("**Reserve first cannot meet the requirement.** With the reserve held back, "
              "energy cannot meet demand.")
    results = {
        "coopt": dict(ok=True, lam_rng=co["lam_range"], pi_rng=co["pi_range"], cost=co["cost"]),
        "ef": dict(ok=ef_ok, lam_rng=ef["lam_range"],
                   pi_rng=ef["res"]["pi_range"] if ef_ok else None,
                   cost=ef["res"]["cost"] if ef_ok else None),
        "rf": dict(ok=rf_ok, lam_rng=rf["lam_range"] if rf_ok else None,
                   pi_rng=rf["pi_range"] if rf_ok else None,
                   cost=rf["res"]["cost"] if rf_ok else None),
    }
    # The run is recorded once per render, before any chart or table is drawn.
    trail = _trail("raise", preset, dict(knobs=(R, batt), R=R, batt=batt, **results))

    with left:
        lam_set = lam_setter(preset, co, batt)
        pi_set = pi_setter(preset, co, batt)
        _show_price(r"Energy price $\lambda$ (\$/MWh)", co["lam_range"], BEYOND_LAM,
                    f"The energy price is {lam_set}." if lam_set else None)
        _show_price(r"Reserve price $\pi^{+}$ (\$/MW/h)", co["pi_range"], _beyond_pi(R),
                    f"The reserve price is {pi_set}." if pi_set else None)
        st.markdown("**Clearing methods to compare**")
        for m in METHODS:
            st.checkbox(METHODS[m], **_kept(f"fc_show_{m}", True))
        shown = [m for m in METHODS if ss[f"fc_show_{m}"]]
        _clear_button("raise", trail)

    with right:
        # The supply curve, with earlier runs as numbered markers.
        pi_pts, lam_pts = [], []
        for e in trail[:-1]:
            c = e["coopt"]
            other = e["batt"] != batt
            where = f"run {e['n']}: R⁺ {_sp(e['R'])} MW, battery {_sp(e['batt'])} MW"
            pi_pts.append((e["n"], e["R"], range_low(c["pi_rng"]),
                           f"{where}, π⁺ {fmt_price(c['pi_rng'], '')[0]}", other))
            lam_pts.append((e["n"], e["R"], range_low(c["lam_rng"]),
                            f"{where}, λ {fmt_price(c['lam_rng'], '')[0]}", other))
        pl, ph = co["pi_range"]
        ll, lh = co["lam_range"]
        pi_text = f"R<sup>+</sup> = {_sp(R)} MW: {PI}<sup>+</sup> {fmt_price(co['pi_range'], '')[0]}"
        lam_text = f"R<sup>+</sup> = {_sp(R)} MW: {LAMBDA} {fmt_price(co['lam_range'], '')[0]}"
        st.plotly_chart(_supply_curve(preset, batt, R, _steps(preset, batt), pl, ll, pi_text,
                                      lam_text, trail=dict(pi=trail_marks(pi_pts),
                                                           lam=trail_marks(lam_pts))),
                        width="stretch")
        st.caption("The reserve supply curve is not the offer stack: a unit's full cost of "
                   "reserve includes the energy margin it gives up, so the cheapest offer is "
                   "not always the cheapest reserve.")

        st.subheader(f"Three clearing methods at R⁺ = {_sp(R)} MW")
        if not shown:
            st.markdown("Tick at least one clearing method to compare them.")
        else:
            _method_table(results, shown)
            if "ef" in shown and not ef_ok:
                st.markdown(ef_msg)
            if "rf" in shown and not rf_ok:
                st.markdown(rf_msg)
            st.caption("Each sequential market sees only one product at a time, so it can only "
                       "cost the same or more.")
            disp = {"coopt": co, "ef": ef["res"] if ef_ok else None,
                    "rf": rf["res"] if rf_ok else None}
            if any(disp[m] is not None for m in shown):
                st.plotly_chart(_dispatch_compare(preset, disp, batt, shown), width="stretch")
            missing = [METHOD_SHORT[m] for m in shown if disp[m] is None]
            if missing:
                st.caption(f"Not drawn, because it cannot meet the requirement: "
                           f"{', '.join(missing).lower()}.")
            current = {m: results[m]["cost"] for m in shown}
            st.plotly_chart(_cost_curves(preset, batt, R, shown, trail, _mcosts(preset, batt),
                                         current), width="stretch")

    # Runs so far, full width.
    st.subheader("Runs so far")
    head = ["Run", r"$R^{+}$ (MW)", "Battery (MW)"]
    for m in shown:
        head += [f"{METHOD_SHORT[m]} $\\lambda$", f"{METHOD_SHORT[m]} $\\pi^{{+}}$",
                 f"{METHOD_SHORT[m]} cost (\\$/h)"]
    rows = []
    for e in trail:
        row = [str(e["n"]), _sp(e["R"]), _sp(e["batt"])]
        for m in shown:
            z = e[m]
            if z["ok"]:
                row += [fmt_price(z["lam_rng"], "")[0], fmt_price(z["pi_rng"], "")[0],
                        _sp(z["cost"])]
            else:
                row += ["cannot meet"] * 3
        rows.append(row)
    _runs_table(head, rows)

    with st.expander("Unit data", expanded=False):
        head = ["Unit", r"$c_k$ (\$/MWh)", r"$\underline{P}_k$ (MW)", r"$\bar{P}_k$ (MW)",
                r"$RR_k$ (MW)", r"$c^{+}_k$ (\$/MW/h)"]
        urows = [[_unit_label(u), _n(u["c"]), _n(u["Pmin"]), _n(u["Pmax"]), _n(u["RR"]),
                  _n(u["cp"])] for u in units]
        st.markdown(_pipe_table(head, urows))
        st.markdown(f"Demand $D$ = {_sp(D)} MW. One five-minute interval, copper plate.")

    with st.expander("The LP and its multipliers", expanded=False):
        obj = r"\min \sum_{k} ( c_k P_k + c^{+}_k r^{+}_k )"
        st.latex(obj + (r" + c^{+}_B r^{+}_B" if batt > 0 else ""))
        st.latex(r"\sum_{k} P_k = D \quad [\lambda]")
        st.latex(r"P_k + r^{+}_k \le \bar{P}_k \quad [\bar{\mu}_k]")
        st.latex(r"P_k \ge \underline{P}_k \quad [\underline{\mu}_k]")
        st.latex(r"0 \le r^{+}_k \le RR_k \quad [\underline{\gamma}_k, \bar{\gamma}_k]")
        if batt > 0:
            st.latex(r"\sum_{k} r^{+}_k + r^{+}_B \ge R^{+} \quad [\pi^{+}]")
            st.latex(rf"0 \le r^{{+}}_B \le {batt} \text{{ MW}}")
        else:
            st.latex(r"\sum_{k} r^{+}_k \ge R^{+} \quad [\pi^{+}]")
        st.latex(r"\lambda = c_k + \bar{\mu}_k - \underline{\mu}_k, \qquad "
                 r"\pi^{+} = c^{+}_k + \bar{\mu}_k + \bar{\gamma}_k - \underline{\gamma}_k")
        st.markdown(r"A unit holding energy above its minimum and reserve strictly inside its "
                    r"limits earns the same margin on both: "
                    r"$\pi^{+} - c^{+}_k = \lambda - c_k = \bar{\mu}_k$.")
        st.markdown("The two sequential methods are two LPs, one after the other. **Energy "
                    "first** dispatches energy alone, then buys reserve only from the headroom "
                    "that is left. **Reserve first** buys reserve alone from each unit's room "
                    r"above its minimum, $\min(RR_k, \bar{P}_k - \underline{P}_k)$, then "
                    "dispatches energy with that capacity held back.")

    with st.expander("Who holds reserve and why", expanded=False):
        v = verdicts(preset, co, batt, unique(co["pi_range"]))
        st.plotly_chart(_full_cost_bars([(a, b, c, d, e) for a, b, c, d, e in v],
                                        co["pi_range"]), width="stretch")
        st.caption("The cheapest offer is not always the cheapest reserve: a full cost "
                   "includes the energy margin the unit gives up.")

    with st.expander("Settlement (co-optimised)", expanded=False):
        if not (unique(co["pi_range"]) and unique(co["lam_range"])):
            st.markdown("At exactly this requirement the prices are not unique, so the "
                        "settlement depends on which side of the breakpoint the market clears. "
                        + nonunique_sentence())
        else:
            _settlement_panel(preset, co, R, batt)


def _method_table(results: dict, shown: list) -> None:
    """One row per ticked method: prices, total cost, and the excess over co-optimised."""
    head = ["Method", r"λ (\$/MWh)", r"π⁺ (\$/MW/h)", r"Total cost (\$/h)",
            r"Per five-minute interval (\$)", r"More than co-optimised (\$/h)"]
    base = results["coopt"]["cost"]
    rows, ranges = [], []
    for m in shown:
        z = results[m]
        if not z["ok"]:
            rows.append([METHOD_SHORT[m]] + ["cannot meet the requirement"] * 3 + ["none", "none"])
            continue
        ranges += [z["lam_rng"], z["pi_rng"]]
        extra = "0" if m == "coopt" else _sp(z["cost"] - base)
        rows.append([METHOD_SHORT[m], fmt_price(z["lam_rng"], "")[0],
                     fmt_price(z["pi_rng"], "")[0], _sp(z["cost"]), _sp(z["cost"] / 12), extra])
    st.markdown(_pipe_table(head, rows))
    if any(r is not None and r[0] is not None and r[1] is not None and not unique(r)
           for r in ranges):
        st.markdown(nonunique_sentence())
    st.caption("For the sequential methods, λ is the energy step price and π⁺ the reserve step "
               "price: each step is priced on its own.")


def _settlement_panel(preset, co, R, batt) -> None:
    sset = settlement(preset, co, R, batt)
    head = ["Unit", r"Energy margin $(\lambda - c_k) P_k$ (\$/h)",
            r"Reserve margin $(\pi^{+} - c^{+}_k) r^{+}_k$ (\$/h)", r"Total (\$/h)"]
    rows = [[r["name"], _n(r["energy"]), _n(r["reserve"]), _n(r["total"])] for r in sset["rows"]]
    st.markdown(_pipe_table(head, rows))
    D = RAISE_PRESETS[preset]["D"]
    st.markdown(rf"Consumers pay $\lambda D$ = {_n(co['lam'])} × {_sp(D)} = **{_sp(sset['consumers'])} "
                rf"\$/h** ({_sp(sset['consumers'] / 12)} \$ per five-minute interval).")
    st.markdown(rf"The reserve bill $\pi^{{+}} R^{{+}}$ = {_n(co['pi'])} × {_n(R)} = "
                rf"**{_sp(sset['bill'])} \$/h** ({_sp(sset['bill'] / 12)} \$ per interval) is "
                "recovered from generators in the NEM (causer pays).")
    for c in sset["checks"]:
        st.markdown(f"{c['name']}: margin on the last MW of energy {_n(c['lam'])} − {_n(c['c'])} = "
                    f"{_n(c['e_margin'])}; on the last MW of reserve {_n(c['pi'])} − {_n(c['cp'])} = "
                    f"{_n(c['r_margin'])}. Equal, so {c['name']} does not want to move capacity "
                    "between the two.")


# --- Mode 2 -----------------------------------------------------------------

def _trap_page() -> None:
    ss = st.session_state
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.radio("Unit", list(TRAP_PRESETS), horizontal=False,
                 format_func=lambda k: TRAP_PRESETS[k]["label"],
                 **_kept("fc_trap_unit", "forum", options=list(TRAP_PRESETS), then=_reset_trap))
        preset = ss["fc_trap_unit"]
        spec = TRAP_PRESETS[preset]
        services = spec["services"]
        st.radio("Service", list(services), horizontal=False,
                 **_kept("fc_service", "Fast raise", options=list(services)))
        service = ss["fc_service"]
        lo, hi = int(spec["P_range"][0]), int(spec["P_range"][1])
        P = int(st.slider(r"Energy target $P_k$ (MW)", lo, hi, step=5,
                          **_kept("fc_P", int(spec["P_default"]), lo, hi)))
        a_raise = int(services["Regulation raise"][4])
        g_raise = int(st.slider(r"Regulation raise enabled $g^{+}_k$ (MW)", 0, a_raise, step=5,
                                **_kept("fc_g_raise", 0, 0, a_raise)))
        g_lower = 0
        if "Regulation lower" in services:
            a_lower = int(services["Regulation lower"][4])
            g_lower = int(st.slider(r"Regulation lower enabled $g^{-}_k$ (MW)", 0, a_lower, step=5,
                                    **_kept("fc_g_lower", 0, 0, a_lower)))
        if "Regulation" in service:
            st.caption("Regulation does not reduce its own availability; the sliders only move "
                       "the contingency rows.")
        cap_r, cap_l = reg_cap(preset, P, "raise"), reg_cap(preset, P, "lower")
        gr, gl = min(float(g_raise), cap_r), min(float(g_lower), cap_l)
        if g_raise > cap_r + EPS:
            st.markdown(rf"Regulation raise is limited to {_mw(cap_r)} MW by its own trapezium "
                        rf"at this energy target, so {_mw(gr)} MW is used.")
        if g_lower > cap_l + EPS:
            st.markdown(rf"Regulation lower is limited to {_mw(cap_l)} MW by its own trapezium "
                        rf"at this energy target, so {_mw(gl)} MW is used.")

        t = services[service]
        Emin, Blo, Bhi, Emax, A = t
        US, LS = slopes(t)
        avail, side = availability(t, P, gr, gl, service)
        inside = Emin - 1e-9 <= P <= Emax + 1e-9
        trail = _trail("trap", preset, dict(knobs=(service, P, g_raise, g_lower), service=service,
                                            P=P, gr=gr, gl=gl, avail=avail, side=side))
        if inside:
            ed.headline(f"Available for {service}", f"{_mw(avail)} MW")
            st.markdown(f"**Available: {_mw(avail)} MW** (the {side} binds)")
        else:
            ed.headline(f"Available for {service}", "0 MW")
            st.markdown(r"The energy target is outside $E^{min}_k$ to $E^{max}_k$, so the unit "
                        "cannot be enabled for this service: 0 MW.")
        _clear_button("trap", trail)

    with right:
        pts = [(e["n"], e["P"], e["avail"],
                f"run {e['n']}: P {_mw(e['P'])} MW, available {_mw(e['avail'])} MW ({e['side']})",
                effective_g(service, e["gr"], e["gl"]) != effective_g(service, gr, gl))
               for e in trail[:-1] if e["service"] == service]
        st.plotly_chart(_trapezium(t, P, gr, gl, service, avail, side if inside else "",
                                   spec["P_range"], trail=trail_marks(pts)), width="stretch")
        st.subheader("Runs so far")
        head = ["Run", "Service", r"$P_k$ (MW)", r"$g^{+}_k$ (MW)"]
        if "Regulation lower" in services:
            head.append(r"$g^{-}_k$ (MW)")
        head += ["Available (MW)", "Row that binds"]
        rows = []
        for e in trail:
            row = [str(e["n"]), e["service"], _mw(e["P"]), _mw(e["gr"])]
            if "Regulation lower" in services:
                row.append(_mw(e["gl"]))
            rows.append(row + [_mw(e["avail"]), e["side"]])
        _runs_table(head, rows)

    with st.expander("The rows", expanded=False):
        st.latex(r"US_k = \frac{E^{max}_k - B^{hi}_k}{A_k}, \qquad "
                 r"LS_k = \frac{B^{lo}_k - E^{min}_k}{A_k}")
        st.latex(r"0 \le r_k \le A_k")
        st.latex(r"P_k + US_k r_k \le E^{max}_k")
        st.latex(r"P_k - LS_k r_k \ge E^{min}_k")
        st.markdown("For **contingency** services only, the joint rows of the lecture (Part IV "
                    "slide 8) add regulation with coefficient 1:")
        st.latex(r"P_k + US_k r^{+}_k + g^{+}_k \le E^{max}_k \qquad \text{(contingency raise)}")
        st.latex(r"P_k - LS_k r^{-}_k - g^{-}_k \ge E^{min}_k \qquad \text{(contingency lower)}")
        st.markdown(rf"{service}: $E^{{min}}_k$ = {_mw(Emin)}, $B^{{lo}}_k$ = {_mw(Blo)}, "
                    rf"$B^{{hi}}_k$ = {_mw(Bhi)}, $E^{{max}}_k$ = {_mw(Emax)}, $A_k$ = {_mw(A)} MW, "
                    rf"so $US_k$ = {_n(US)} and $LS_k$ = {_n(LS)}.")

    with st.expander("Step by step", expanded=False):
        if not inside:
            st.markdown(r"The energy target is outside $E^{min}_k$ to $E^{max}_k$, so the unit "
                        "cannot be enabled for this service: 0 MW.")
        else:
            for step in trap_steps(t, P, gr, gl, service):
                if step["value"] is None:
                    st.markdown(f"- {step['label']}: vertical side: no limit from this row")
                else:
                    mark = " **(smallest)**" if step["row"] == side else ""
                    st.markdown(f"- {step['label']}: ${step['tex']}$ MW{mark}")

    with st.expander("All services at this energy target", expanded=False):
        st.plotly_chart(_trap_multiples(preset, P, gr, gl), width="stretch")
        table = []
        for name, tt in services.items():
            a, sd = availability(tt, P, *effective_g(name, gr, gl), service=name)
            table.append([name, _mw(a), sd])
        st.markdown(_pipe_table(["Service", "Availability (MW)", "Row that binds"], table))
        if preset == "forum":
            st.caption("Near the top of its range a unit runs out of contingency raise; near the "
                       "bottom it runs out of lower. This unit offers no very fast services.")
        elif preset == "battery":
            st.caption("Raise while charging means stop charging, then discharge; lower while "
                       "discharging means stop discharging, then charge. NEMDE does not check the "
                       "stored energy needed to sustain the response: the battery's owner must.")


# --- Mode 3 -----------------------------------------------------------------

def _lower_page() -> None:
    ss = st.session_state
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.radio("Preset", list(LOWER_PRESETS), horizontal=False,
                 format_func=lambda k: LOWER_PRESETS[k]["label"],
                 **_kept("fc_lower_preset", "forum_midday", options=list(LOWER_PRESETS),
                         then=_reset_lower))
        preset = ss["fc_lower_preset"]
        p = LOWER_PRESETS[preset]
        units = p["units"]
        step = 5 if preset == "forum_midday" else 10
        Rm = int(st.slider(r"Contingency lower requirement $R^{-}$ (MW)", 0, int(p["R_max"]),
                           step=step, **_kept("fc_Rm", int(p["R_default"]), 0, int(p["R_max"]))))
    s = _lower(preset, Rm)
    if s is None:
        with right:
            ed.note(f"**No feasible dispatch.** The requirement of {_sp(Rm)} MW cannot be met.")
        return
    trail = _trail("lower", preset, dict(knobs=(Rm,), Rm=Rm, lam_rng=s["lam_range"],
                                         pi_rng=s["pi_range"], P=list(s["P"]), r=list(s["r"])))
    beyond = (f"There is no feasible dispatch above {_sp(Rm)} MW, so the price has no "
              "right-hand value.")
    with left:
        _show_price(r"Energy price $\lambda$ (\$/MWh)", s["lam_range"], BEYOND_LAM, None)
        _show_price(r"Lower price $\pi^{-}$ (\$/MW/h)", s["pi_range"], beyond, None)
        _clear_button("lower", trail)

    with right:
        pts = [(e["n"], e["Rm"], range_low(e["pi_rng"]),
                f"run {e['n']}: R⁻ {_sp(e['Rm'])} MW, π⁻ {fmt_price(e['pi_rng'], '')[0]}", False)
               for e in trail[:-1]]
        pl = s["pi_range"][0]
        text = f"R<sup>\u2212</sup> = {_sp(Rm)} MW: {PI}<sup>\u2212</sup> {fmt_price(s['pi_range'], '')[0]}"
        st.plotly_chart(_lower_steps(_lsteps(preset), Rm, pl, text, trail=trail_marks(pts)),
                        width="stretch")
        st.plotly_chart(_lower_bars(preset, s), width="stretch")
        ls = lower_setter(preset, s)
        if ls is not None and unique(s["pi_range"]) and unique(s["lam_range"]):
            st.latex(rf"\pi^{{-}} = c^{{-}}_k + ( c_k - \lambda ) = {_m(ls['cm'])} + "
                     rf"({_m(ls['c'])} - {_m(ls['lam'])}) = {_m(ls['pi'])}")
            who = "The gas unit" if ls["name"] == "Gas" else ls["name"]
            st.markdown(f"{who} must run above the level it would choose at $\\lambda$ = "
                        f"{_n(ls['lam'])} \\$/MWh, and loses {_n(ls['c'])} − {_n(ls['lam'])} = "
                        f"{_n(ls['c'] - ls['lam'])} on each extra MWh. Lower FCAS is expensive "
                        "exactly when energy is cheap.")

    st.subheader("Runs so far")
    lower_units = [(k, u) for k, u in enumerate(units) if u["RRlow"] > 0]
    head = ["Run", r"$R^{-}$ (MW)", r"$\lambda$ (\$/MWh)", r"$\pi^{-}$ (\$/MW/h)"]
    head += [f"{u['name']} $P_k$ (MW)" for u in units]
    head += [f"{u['name']} $r^{{-}}_k$ (MW)" for _, u in lower_units]
    rows = []
    for e in trail:
        row = [str(e["n"]), _sp(e["Rm"]), fmt_price(e["lam_rng"], "")[0],
               fmt_price(e["pi_rng"], "")[0]]
        row += [_mw(v) for v in e["P"]]
        row += [_mw(e["r"][k]) for k, _ in lower_units]
        rows.append(row)
    _runs_table(head, rows)

    with st.expander("Unit data", expanded=False):
        head = ["Unit", r"$c_k$ (\$/MWh)", r"$\underline{P}_k$ (MW)", r"$\bar{P}_k$ (MW)",
                r"Lower offered (MW)", r"$c^{-}_k$ (\$/MW/h)"]
        urows = [[u["name"], _n(u["c"]), _n(u["Pmin"]), _n(u["Pmax"]),
                  _n(u["RRlow"]) if u["RRlow"] > 0 else "none",
                  _n(u["cm"]) if u["RRlow"] > 0 else "none"] for u in units]
        st.markdown(_pipe_table(head, urows))
        st.markdown(f"Demand $D$ = {_sp(p['D'])} MW. One five-minute interval, copper plate.")
    with st.expander("The LP and its multipliers", expanded=False):
        st.latex(r"\min \sum_{k} ( c_k P_k + c^{-}_k r^{-}_k )")
        st.latex(r"\sum_{k} P_k = D \quad [\lambda]")
        st.latex(r"P_k - r^{-}_k \ge \underline{P}_k \quad [\underline{\mu}_k]")
        st.latex(r"0 \le r^{-}_k \le RR^{-}_k, \qquad \sum_{k} r^{-}_k \ge R^{-} \quad [\pi^{-}]")


# --- Mode 4 -----------------------------------------------------------------

def _gl_page() -> None:
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.markdown(r"Mainland providers offer 500 MW at 3 \$/MW/h. South Australian providers "
                    r"offer 40 MW at 10 and 60 MW at 50 \$/MW/h. The global requirement is fixed "
                    r"at $R^{G}$ = 400 MW.")
        R_SA = int(st.slider(r"South Australian local requirement $R^{SA}$ (MW)", 0, 100, step=10,
                             **_kept("fc_RSA", 80, 0, 100)))
    s = _gl(R_SA)
    if s is None:
        with right:
            ed.note("**No feasible dispatch.**")
        return
    trail = _trail("gl", "gl", dict(knobs=(R_SA,), R_SA=R_SA, piG_rng=s["piG_range"],
                                    piSA_rng=s["piSA_range"], sa_rng=s["sa_range"],
                                    y=sa_stack_price(R_SA)))
    beyond = (f"There is no feasible dispatch above {_sp(R_SA)} MW of local requirement, so the "
              "price has no right-hand value.")
    with left:
        _show_price(r"Global price $\pi^{G}$ (\$/MW/h)", s["piG_range"], beyond, None)
        _show_price(r"South Australian row price $\pi^{SA}$ (\$/MW/h)", s["piSA_range"], beyond,
                    None)
        sa_head, _ = fmt_price(s["sa_range"], beyond)
        pg_head = fmt_price(s["piG_range"], beyond)[0]
        if unique(s["sa_range"]) and unique(s["piG_range"]):
            st.markdown(rf"Regional prices: mainland $\pi^{{G}}$ = **{pg_head}** \$/MW/h; South "
                        rf"Australia $\pi^{{G}} + \pi^{{SA}}$ = {_n(s['piG'])} + {_n(s['piSA'])} = "
                        rf"**{sa_head}** \$/MW/h.")
        else:
            st.markdown(rf"Regional prices: mainland $\pi^{{G}}$ = **{pg_head}** \$/MW/h; South "
                        rf"Australia $\pi^{{G}} + \pi^{{SA}}$ is **{sa_head}** \$/MW/h.")
        _clear_button("gl", trail)

    with right:
        pts = [(e["n"], e["R_SA"], e["y"],
                f"run {e['n']}: R<sup>SA</sup> {_mw(e['R_SA'])} MW, South Australian price "
                f"{fmt_price(e['sa_rng'], '')[0]}", False) for e in trail[:-1]]
        st.plotly_chart(_sa_curve(R_SA, s["piG"], "", trail=trail_marks(pts)), width="stretch")
        rows = [[q["name"], q["region"] if q["region"] == "SA" else "NEM", _n(q["mw"]),
                 _n(q["price"]), _n(x)] for q, x in zip(LOCAL["providers"], s["x"])]
        st.markdown(_pipe_table(["Provider", "Region", "Offered (MW)", r"Offer (\$/MW/h)",
                                 "Enabled (MW)"], rows))

    st.subheader("Runs so far")
    head = ["Run", r"$R^{SA}$ (MW)", r"$\pi^{G}$ (\$/MW/h)", r"$\pi^{SA}$ (\$/MW/h)",
            r"South Australian price $\pi^{G} + \pi^{SA}$ (\$/MW/h)"]
    rows = [[str(e["n"]), _mw(e["R_SA"]), fmt_price(e["piG_rng"], "")[0],
             fmt_price(e["piSA_rng"], "")[0], fmt_price(e["sa_rng"], "")[0]] for e in trail]
    _runs_table(head, rows)
    ed.note("In January and February 2020 South Australia was separated from the NEM for about "
            "18 days. Its FCAS had to come from inside the region, so the local rows bound, and "
            "South Australian fast raise reached the 14 700 $/MW/h market price cap for 365 "
            "minutes.")
    with st.expander("The rows and their multipliers", expanded=False):
        st.latex(r"\sum_{k \in NEM} r_k \ge R^{G} \quad [\pi^{G}], \qquad "
                 r"\sum_{k \in SA} r_k \ge R^{SA} \quad [\pi^{SA}]")
