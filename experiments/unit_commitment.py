"""One unit commitment model, growing in layers (Topic 8).

Six stages of the lecture running example, each adding rows to the last: UC,
then minimum up and down times, then a battery, then SCUC (reserve and a
generation N-1 rule), then NCUC (the Topic 7 DC network inside the SCUC) in two
cases. Every stage is solved as a mixed integer program with scipy's HiGHS
(milp, mip_rel_gap = 0). The nodal prices come from a pricing run: every
binary is fixed at its MILP value and the remaining LP is re-solved with
linprog.

Everything is in actual units: MW, MWh, $/MWh, $/h, $, ohms, MW/rad, and one
hour per interval so MW and MWh are numerically equal. The units, the battery,
the demand and the network are constants here; students only move two knobs:
the hour-by-hour (no look-ahead) toggle on stage 1 and G3's minimum up time.

Notation as the lectures write it: u, y, z for on, start and stop, P for
output, r for reserve, w for the battery mode, lambda for the balance
multiplier and pi for the N-1 multiplier. Scipy's marginals are
d(objective)/d(rhs), so lambda and pi come straight off the pricing run's rows.
Flow direction: line (a, b) is positive from a to b.

Several optima are degenerate (equal-cost schedules exist), so only the
robust facts are pinned in the tests.
"""
from __future__ import annotations

import math
from itertools import product

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import hstack, lil_matrix, vstack

from experiments._kit import ed

EPS = 1e-6
HOURS = tuple(range(1, 9))
UNITS = ("G1", "G2", "G3", "G4")
UNIT_NAMES = {"G1": "G1 CCGT", "G2": "G2 coal", "G3": "G3 gas", "G4": "G4 OCGT"}
LINES = ("1-2", "1-3", "2-3")
LAMBDA = ed.LAMBDA


def _z(x) -> float:
    """HiGHS round-off and -0.0 off a number students read."""
    x = float(x)
    return 0.0 if abs(x) < 1e-9 else x


# --- The lecture running example --------------------------------------------

def data(ut_g3: int = 3, f23: float = 800.0) -> dict:
    """The Topic 8 data, with the two things a student may change or switch."""
    g = dict(
        c={"G1": 40, "G2": 20, "G3": 50, "G4": 110},
        Pmin={"G1": 600, "G2": 500, "G3": 450, "G4": 60},
        Pmax={"G1": 1500, "G2": 1000, "G3": 1500, "G4": 320},
        NL={"G1": 4000, "G2": 3000, "G3": 2500, "G4": 500},
        CSU={"G1": 20000, "G2": 60000, "G3": 15000, "G4": 3000},
        RU={"G1": 600, "G2": 300, "G3": 500, "G4": 320},
        RD={"G1": 600, "G2": 300, "G3": 500, "G4": 320},
        SU={"G1": 600, "G2": 500, "G3": 450, "G4": 320},
        SD={"G1": 600, "G2": 500, "G3": 450, "G4": 320},
        UT={"G1": 4, "G2": 8, "G3": int(ut_g3), "G4": 1},
        DT={"G1": 3, "G2": 8, "G3": 2, "G4": 1},
        RR={"G1": 450, "G2": 150, "G3": 500, "G4": 300},
        u0={"G1": 1, "G2": 1, "G3": 0, "G4": 0},
        P0={"G1": 700, "G2": 900, "G3": 0, "G4": 0},
        h0={"G1": 10, "G2": 24, "G3": 10, "G4": 10},
        bus={"G1": 1, "G2": 2, "G3": 3, "G4": 3},
    )
    return dict(U=list(UNITS), g=g, D=[1500, 1400, 1450, 1700, 2100, 2600, 2800, 2400],
                D1=300, PB=400, EB=800, eta=0.95, E0=400, B=330 ** 2 / 21.78,
                lines=[(1, 2), (1, 3), (2, 3)],
                F={(1, 2): 1500, (1, 3): 1500, (2, 3): float(f23)})


STAGES = [
    dict(n=1, label="UC", kw=dict(), f23=800.0,
         adds="Choose which units run each hour and how much each produces, paying for "
              "energy, no-load and start-ups. Every later stage adds rows to this one."),
    dict(n=2, label="+ minimum up and down times", kw=dict(minud=True), f23=800.0,
         adds="A unit can no longer be switched on and off every hour. Minimum up and "
              "down times also carry in how long each unit has already been in its state."),
    dict(n=3, label="+ battery", kw=dict(minud=True, bat=True), f23=800.0,
         adds="A battery at bus 3, with a mode binary so it cannot charge and discharge "
              "at once. It is a new resource, so it can lower the cost."),
    dict(n=4, label="SCUC", kw=dict(minud=True, bat=True, res=True), f23=800.0,
         adds="Reserve and an N-1 rule: whichever generator trips, the others' reserve "
              "must cover its output. This needs more units committed."),
    dict(n=5, label="NCUC, Case A", kw=dict(minud=True, bat=True, res=True, net=True), f23=800.0,
         adds="The single balance becomes the Topic 7 three-bus DC network, with flows "
              "and line ratings (line 2-3 at 800 MW)."),
    dict(n=6, label="NCUC, Case B", kw=dict(minud=True, bat=True, res=True, net=True), f23=700.0,
         adds="The same as Case A with line 2-3 cut to 700 MW. The SCUC schedule can no "
              "longer be dispatched, so the commitment has to change."),
]


# --- The model, row for row as the lectures write it ------------------------

class Model:
    def __init__(s):
        s.ix = {}
        s.lb = []
        s.ub = []
        s.integ = []
        s.rows = []

    def v(s, n, lb=0, ub=np.inf, b=False):
        s.ix[n] = len(s.lb)
        s.lb.append(lb)
        s.ub.append(ub)
        s.integ.append(1 if b else 0)

    def row(s, terms, lo, hi, name):
        s.rows.append((terms, lo, hi, name))


def build(d, minud=False, bat=False, res=False, net=False, fix=None) -> Model:
    g = d["g"]
    U = d["U"]
    T = range(1, 9)
    m = Model()
    obj = {}
    for t in T:
        for k in U:
            m.v(f"P_{k}_{t}", 0, g["Pmax"][k])
            m.v(f"r_{k}_{t}", 0, g["RR"][k] if res else 0)
            for b in "uyz":
                m.v(f"{b}_{k}_{t}", 0, 1, True)
            obj[f"P_{k}_{t}"] = g["c"][k]
            obj[f"u_{k}_{t}"] = g["NL"][k]
            obj[f"y_{k}_{t}"] = g["CSU"][k]
        m.v(f"Pc_{t}", 0, d["PB"] if bat else 0)
        m.v(f"Pd_{t}", 0, d["PB"] if bat else 0)
        m.v(f"E_{t}", 0, d["EB"])
        m.v(f"rB_{t}", 0, d["PB"] if (bat and res) else 0)
        m.v(f"w_{t}", 0, 1 if bat else 0, True)
        if net:
            for (a, b) in d["lines"]:
                m.v(f"f_{a}{b}_{t}", -d["F"][(a, b)], d["F"][(a, b)])
            for i in (1, 2):
                m.v(f"dl_{i}_{t}", -np.pi, np.pi)
    for k in U:  # carry-in from the initial state
        Lup = max(0, g["UT"][k] - g["h0"][k]) if g["u0"][k] == 1 else 0
        Ldn = max(0, g["DT"][k] - g["h0"][k]) if g["u0"][k] == 0 else 0
        for t in T:
            if minud and t <= Lup:
                m.lb[m.ix[f"u_{k}_{t}"]] = 1
            if minud and t <= Ldn:
                m.ub[m.ix[f"u_{k}_{t}"]] = 0
    for t in T:
        if not net:
            m.row([(f"P_{k}_{t}", 1) for k in U] + [(f"Pd_{t}", 1), (f"Pc_{t}", -1)],
                  d["D"][t - 1], d["D"][t - 1], f"bal_{t}")
        else:
            Dbus = {1: d["D1"], 2: 0, 3: d["D"][t - 1] - d["D1"]}
            for i in (1, 2, 3):
                te = [(f"P_{k}_{t}", 1) for k in U if g["bus"][k] == i]
                if i == 3:
                    te += [(f"Pd_{t}", 1), (f"Pc_{t}", -1)]
                for (a, b) in d["lines"]:
                    if a == i:
                        te.append((f"f_{a}{b}_{t}", -1))
                    if b == i:
                        te.append((f"f_{a}{b}_{t}", 1))
                m.row(te, Dbus[i], Dbus[i], f"bal{i}_{t}")
            for (a, b) in d["lines"]:
                te = [(f"f_{a}{b}_{t}", 1)]
                if a != 3:
                    te.append((f"dl_{a}_{t}", -d["B"]))
                if b != 3:
                    te.append((f"dl_{b}_{t}", d["B"]))
                m.row(te, 0, 0, f"flow{a}{b}_{t}")
        for k in U:
            m.row([(f"P_{k}_{t}", 1), (f"r_{k}_{t}", 1), (f"u_{k}_{t}", -g["Pmax"][k])],
                  -np.inf, 0, f"capup_{k}_{t}")
            m.row([(f"P_{k}_{t}", 1), (f"u_{k}_{t}", -g["Pmin"][k])], 0, np.inf, f"caplo_{k}_{t}")
            te = [(f"y_{k}_{t}", 1), (f"z_{k}_{t}", -1), (f"u_{k}_{t}", -1)]
            rhs = 0
            if t > 1:
                te.append((f"u_{k}_{t - 1}", 1))
            else:
                rhs = -g["u0"][k]
            m.row(te, rhs, rhs, f"logic_{k}_{t}")
            m.row([(f"y_{k}_{t}", 1), (f"z_{k}_{t}", 1)], -np.inf, 1, f"yz_{k}_{t}")
            te = [(f"P_{k}_{t}", 1), (f"y_{k}_{t}", -g["SU"][k])]
            if t > 1:
                te += [(f"P_{k}_{t - 1}", -1), (f"u_{k}_{t - 1}", -g["RU"][k])]
                hi = 0
            else:
                hi = g["P0"][k] + g["RU"][k] * g["u0"][k]
            m.row(te, -np.inf, hi, f"rup_{k}_{t}")
            te = [(f"P_{k}_{t}", -1), (f"u_{k}_{t}", -g["RD"][k]), (f"z_{k}_{t}", -g["SD"][k])]
            if t > 1:
                te.append((f"P_{k}_{t - 1}", 1))
                hi = 0
            else:
                hi = -g["P0"][k]
            m.row(te, -np.inf, hi, f"rdn_{k}_{t}")
            if minud:
                te = [(f"y_{k}_{tt}", 1) for tt in range(max(1, t - g["UT"][k] + 1), t + 1)]
                m.row(te + [(f"u_{k}_{t}", -1)], -np.inf, 0, f"mup_{k}_{t}")
                te = [(f"z_{k}_{tt}", 1) for tt in range(max(1, t - g["DT"][k] + 1), t + 1)]
                m.row(te + [(f"u_{k}_{t}", 1)], -np.inf, 1, f"mdn_{k}_{t}")
        if bat:
            e = d["eta"]
            te = [(f"E_{t}", 1), (f"Pc_{t}", -e), (f"Pd_{t}", 1 / e)]
            if t > 1:
                te.append((f"E_{t - 1}", -1))
                rhs = 0
            else:
                rhs = d["E0"]
            m.row(te, rhs, rhs, f"soe_{t}")
            m.row([(f"Pc_{t}", 1), (f"w_{t}", -d["PB"])], -np.inf, 0, f"chm_{t}")
            m.row([(f"Pd_{t}", 1), (f"w_{t}", d["PB"])], -np.inf, d["PB"], f"dim_{t}")
            if res:
                m.row([(f"rB_{t}", 1), (f"Pd_{t}", 1), (f"Pc_{t}", -1)], -np.inf, d["PB"], f"rBc_{t}")
                m.row([(f"rB_{t}", 1 / e), (f"E_{t}", -1)], -np.inf, 0, f"rBe_{t}")
        else:
            m.ub[m.ix[f"E_{t}"]] = 0
        if res:
            for k in U:
                m.row([(f"r_{j}_{t}", 1) for j in U if j != k] + [(f"rB_{t}", 1), (f"P_{k}_{t}", -1)],
                      0, np.inf, f"n1_{k}_{t}")
    if bat:
        m.row([("E_8", 1)], d["E0"], np.inf, "Eend")
    if fix:
        for n, val in fix.items():
            m.lb[m.ix[n]] = val
            m.ub[m.ix[n]] = val
    n = len(m.lb)
    c = np.zeros(n)
    for k, val in obj.items():
        c[m.ix[k]] = val
    A = lil_matrix((len(m.rows), n))
    lo = []
    hi = []
    for r, (te, l, h, _) in enumerate(m.rows):
        for v, a in te:
            A[r, m.ix[v]] += a
        lo.append(l)
        hi.append(h)
    m.c = c
    m.A = A.tocsr()
    m.rlo = np.array(lo, float)
    m.rhi = np.array(hi, float)
    return m


def _milp(m: Model, relax: bool = False):
    integ = np.zeros(len(m.lb)) if relax else np.array(m.integ)
    return milp(m.c, constraints=LinearConstraint(m.A, m.rlo, m.rhi), integrality=integ,
                bounds=Bounds(m.lb, m.ub), options=dict(mip_rel_gap=0))


def _binaries(x: dict) -> dict:
    return {n: round(v) for n, v in x.items() if n.split("_")[0] in ("u", "y", "z", "w")}


def _view(x: dict, d: dict) -> dict:
    """The solution as lists indexed by hour 0..7, for the page and the trip check."""
    def series(prefix, k=None):
        return [_z(x[f"{prefix}_{k}_{t}" if k else f"{prefix}_{t}"]) for t in HOURS]

    def flags(prefix):
        return {k: [round(x[f"{prefix}_{k}_{t}"]) for t in HOURS] for k in UNITS}

    v = dict(P={k: series("P", k) for k in UNITS}, r={k: series("r", k) for k in UNITS},
             u=flags("u"), y=flags("y"), z=flags("z"),
             Pd=series("Pd"), Pc=series("Pc"), E=series("E"), rB=series("rB"),
             w=[round(x[f"w_{t}"]) for t in HOURS], f={})
    if "f_12_1" in x:
        v["f"] = {f"{a}-{b}": series(f"f_{a}{b}") for a, b in d["lines"]}
    return v


def _costs(v: dict, d: dict) -> dict:
    g = d["g"]
    en = sum(g["c"][k] * p for k in UNITS for p in v["P"][k])
    nl = sum(g["NL"][k] * u for k in UNITS for u in v["u"][k])
    su = sum(g["CSU"][k] * y for k in UNITS for y in v["y"][k])
    return dict(energy=en, noload=nl, startup=su, total=en + nl + su)


def _sched(v: dict) -> dict:
    return {k: "".join(str(u) for u in v["u"][k]) for k in UNITS}


def solve_stage(stage: int, ut_g3: int = 3) -> dict:
    """One stage as a MILP. Stage 1 has no minimum up or down rows, so it ignores UT."""
    s = STAGES[stage - 1]
    d = data(ut_g3 if s["kw"].get("minud") else 3, s["f23"])
    m = build(d, **s["kw"])
    r = _milp(m)
    if r.status != 0:
        return dict(ok=False)
    x = {n: float(r.x[i]) for n, i in m.ix.items()}
    v = _view(x, d)
    return dict(ok=True, x=x, view=v, costs=_costs(v, d), sched=_sched(v))


def hour_by_hour_result() -> dict:
    """Each hour chosen on its own, given the state the previous hour left (no look-ahead)."""
    d = data()
    g = d["g"]
    state = {k: (g["u0"][k], g["P0"][k]) for k in UNITS}
    P = {k: [] for k in UNITS}
    u = {k: [] for k in UNITS}
    y = {k: [] for k in UNITS}
    z = {k: [] for k in UNITS}
    for t in HOURS:
        D = d["D"][t - 1]
        best = None
        for on in product([0, 1], repeat=len(UNITS)):
            uu = dict(zip(UNITS, on))
            lo = {}
            hi = {}
            ok = True
            for k in UNITS:
                u0, P0 = state[k]
                lo[k] = g["Pmin"][k] * uu[k]
                hi[k] = g["Pmax"][k] * uu[k]
                if uu[k] and not u0:
                    hi[k] = min(hi[k], g["SU"][k])
                if uu[k] and u0:
                    hi[k] = min(hi[k], P0 + g["RU"][k])
                    lo[k] = max(lo[k], P0 - g["RD"][k])
                if not uu[k] and u0 and P0 > g["SD"][k]:
                    ok = False
                if lo[k] > hi[k] + 1e-9:
                    ok = False
            if not ok or sum(lo.values()) > D or sum(hi.values()) < D:
                continue
            p = dict(lo)
            rem = D - sum(lo.values())
            for k in sorted(UNITS, key=lambda k: g["c"][k]):
                a = min(rem, hi[k] - p[k])
                p[k] += a
                rem -= a
            cost = sum(g["c"][k] * p[k] + g["NL"][k] * uu[k]
                       + g["CSU"][k] * (uu[k] and not state[k][0]) for k in UNITS)
            if best is None or cost < best[0]:
                best = (cost, uu, p)
        _, uu, p = best
        for k in UNITS:
            P[k].append(_z(p[k]))
            u[k].append(int(uu[k]))
            y[k].append(int(uu[k] and not state[k][0]))
            z[k].append(int(state[k][0] and not uu[k]))
            state[k] = (uu[k], p[k])
    zeros = [0.0] * 8
    v = dict(P=P, r={k: zeros for k in UNITS}, u=u, y=y, z=z, Pd=zeros, Pc=zeros, E=zeros,
             rB=zeros, w=[0] * 8, f={})
    return dict(ok=True, view=v, costs=_costs(v, d), sched=_sched(v))


# --- Pricing run and settlement ---------------------------------------------

def price_run(d: dict, x: dict, **kw) -> dict:
    """Fix every binary at its MILP value, re-solve the LP, read the multipliers."""
    m = build(d, fix=_binaries(x), **kw)
    eq = m.rlo == m.rhi
    Aeq = m.A[eq]
    beq = m.rlo[eq]
    Aub_list = []
    bub = []
    names = []
    idx_eq = np.where(eq)[0]
    for r in np.where(~eq)[0]:
        if np.isfinite(m.rhi[r]):
            Aub_list.append(m.A[r])
            bub.append(m.rhi[r])
            names.append((r, 1))
        if np.isfinite(m.rlo[r]):
            Aub_list.append(-m.A[r])
            bub.append(-m.rlo[r])
            names.append((r, -1))
    res = linprog(m.c, A_ub=vstack(Aub_list), b_ub=bub, A_eq=Aeq, b_eq=beq,
                  bounds=list(zip(m.lb, m.ub)), method="highs")
    if not res.success:
        return dict(ok=False)
    duals = {}
    for j, r in enumerate(idx_eq):
        duals[m.rows[r][3]] = res.eqlin.marginals[j]
    for j, (r, sgn) in enumerate(names):
        duals[m.rows[r][3]] = duals.get(m.rows[r][3], 0) + sgn * res.ineqlin.marginals[j]
    return dict(ok=True, duals=duals, obj=res.fun)


def settlement(d: dict, v: dict, lam: dict, total: float) -> dict:
    """Pay each unit its nodal price for its MILP schedule and compare with its offer."""
    g = d["g"]
    gens = {}
    revenue_all = 0.0
    for k in UNITS:
        revenue = sum(p * lam[g["bus"][k]][t] for t, p in enumerate(v["P"][k]))
        cost = sum(g["c"][k] * v["P"][k][t] + g["NL"][k] * v["u"][k][t]
                   + g["CSU"][k] * v["y"][k][t] for t in range(8))
        profit = revenue - cost
        gens[k] = dict(revenue=revenue, cost=cost, profit=profit, uplift=max(0.0, -profit))
        revenue_all += revenue
    battery = sum((v["Pd"][t] - v["Pc"][t]) * lam[3][t] for t in range(8))
    consumers = sum(lam[1][t] * d["D1"] + lam[3][t] * (d["D"][t] - d["D1"]) for t in range(8))
    uplift = sum(r["uplift"] for r in gens.values())
    return dict(gens=gens, battery=battery, consumers=consumers,
                rent=consumers - revenue_all - battery, uplift=uplift,
                share=uplift / total, total=total)


def prices(stage: int, ut_g3: int = 3) -> dict:
    """The pricing run for stage 5 or 6, on that stage's own binaries and rating."""
    res = solve_stage(stage, ut_g3)
    if not res["ok"]:
        return dict(ok=False)
    s = STAGES[stage - 1]
    d = data(ut_g3 if s["kw"].get("minud") else 3, s["f23"])
    pr = price_run(d, res["x"], **s["kw"])
    if not pr["ok"]:
        return dict(ok=False)
    lam = {i: [_z(pr["duals"][f"bal{i}_{t}"]) for t in HOURS] for i in (1, 2, 3)}
    n1 = [_z(pr["duals"][f"n1_G3_{t}"]) for t in HOURS]
    return dict(ok=True, lam=lam, n1_g3=n1,
                settlement=settlement(d, res["view"], lam, res["costs"]["total"]))


def stage4_schedule_feasible_in_case_b() -> bool:
    """Fix stage 4's binaries in the stage 6 network: can that schedule still be dispatched?"""
    base = solve_stage(4)
    d = data(3, 700.0)
    m = build(d, **STAGES[5]["kw"], fix=_binaries(base["x"]))
    return _milp(m, relax=True).status == 0


def max_hour7_demand_case_b() -> float:
    """The largest hour 7 demand (MW) that stage 4's schedule can serve in the Case B network.

    One LP: the binaries are fixed, and a free variable adds to the bus 3 demand
    in hour 7, which is then maximised.
    """
    base = solve_stage(4)
    d = data(3, 700.0)
    m = build(d, **STAGES[5]["kw"], fix=_binaries(base["x"]))
    row = next(r for r, (_, _, _, name) in enumerate(m.rows) if name == "bal3_7")
    col = lil_matrix((len(m.rows), 1))
    col[row, 0] = -1.0
    A = hstack([m.A, col.tocsr()]).tocsr()
    c = np.append(m.c * 0.0, -1.0)
    r = milp(c, constraints=LinearConstraint(A, m.rlo, m.rhi), integrality=np.zeros(len(c)),
             bounds=Bounds(np.append(m.lb, -3000.0), np.append(m.ub, 3000.0)))
    return float(d["D"][6] - r.fun)


# --- Trip check -------------------------------------------------------------

def trip(v: dict, stage: int, t: int, k: str, include: dict | None = None) -> dict:
    """Trip unit k in hour t (1 to 8) of the schedule v.

    Each survivor offers its capability within 10 minutes, not the reserve the
    solver happened to schedule: a committed generator j gives
    min(RR_j, Pmax_j - P_j,t), an uncommitted one 0, and the battery (stage 3
    on) min(Pdis-bar, Pdis-bar - (Pdis_t - Pch_t), eta E_t).
    """
    d = data()
    g = d["g"]
    i = t - 1
    include = include or {}
    if not v["u"][k][i]:
        return dict(committed=False, lost=0.0, rows=[], available=0.0, ok=True, shortfall=0.0)
    lost = v["P"][k][i]
    rows = []
    for j in UNITS:
        if j == k:
            continue
        on = bool(v["u"][j][i])
        cap = min(g["RR"][j], g["Pmax"][j] - v["P"][j][i]) if on else 0.0
        rows.append(dict(name=j, committed=on, scheduled=v["P"][j][i], capability=cap,
                         included=include.get(j, True)))
    if stage >= 3:
        net = v["Pd"][i] - v["Pc"][i]
        cap = max(0.0, min(d["PB"], d["PB"] - net, d["eta"] * v["E"][i]))
        rows.append(dict(name="BESS", committed=True, scheduled=net, capability=cap,
                         included=include.get("BESS", True)))
    for row in rows:
        row["contribution"] = row["capability"] if row["included"] else 0.0
    available = sum(row["contribution"] for row in rows)
    return dict(committed=True, lost=lost, rows=rows, available=available,
                ok=available >= lost - EPS, shortfall=max(0.0, lost - available))


# --- Formatting -------------------------------------------------------------

def _n(x: float) -> str:
    """Two decimals, and no trailing .00 on an integer."""
    s = f"{round(float(x), 2) + 0.0:,.2f}"
    return s[:-3] if s.endswith(".00") else s


def _sp(x: float) -> str:
    """A whole number with a space between thousands, as the lecture sentences write it."""
    return f"{x:,.0f}".replace(",", " ")


def _pipe_table(head: list[str], rows: list[list[str]]) -> str:
    """A markdown table, so its cells reach KaTeX."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


# --- The rows each stage adds -----------------------------------------------

OBJECTIVE = r"\min \sum_{t} \sum_{k} \left( c_k P_{k,t} \Delta T + C^{NL}_k u_{k,t} \Delta T " \
            r"+ C^{SU}_k y_{k,t} + C^{SD}_k z_{k,t} \right)"

# group -> variant -> (title, [LaTeX], meaning)
VARIANTS = {
    "objective": {"all": (
        "Objective", [OBJECTIVE],
        "Energy, no-load and start-up cost over all eight hours (shut-down cost is zero here).")},
    "balance": {
        "copper": ("Balance, copper plate", [r"\sum_k P_{k,t} = D_t \quad [\lambda_t]"],
                   "Generation equals demand in every hour. One price, no network."),
        "battery": ("Balance with the battery",
                    [r"\sum_k P_{k,t} + P^{dis}_t - P^{ch}_t = D_t \quad [\lambda_t]"],
                    "The battery's discharge counts as supply and its charging as demand."),
        "network": ("Nodal balance",
                    [r"\sum_{k \in gen(i)} P_{k,t} - D_{i,t} - \sum_{\ell \in out(i)} f_{\ell,t} "
                     r"+ \sum_{\ell \in in(i)} f_{\ell,t} = 0 \quad [\lambda_{i,t}]"],
                    "Each bus balances its own generation, load and line flows, so every bus "
                    "has its own price. The battery injects at bus 3."),
    },
    "capacity": {
        "plain": ("Capacity", [r"\underline{P}_k u_{k,t} \le P_{k,t}",
                               r"P_{k,t} \le \bar{P}_k u_{k,t}"],
                  "A unit produces between its minimum and maximum when on, and nothing when off."),
        "reserve": ("Capacity with reserve", [r"\underline{P}_k u_{k,t} \le P_{k,t}",
                                              r"P_{k,t} + r_{k,t} \le \bar{P}_k u_{k,t}"],
                    "Output plus the reserve the unit holds must fit under its maximum."),
    },
    "logic": {"all": (
        "Logic", [r"y_{k,t} - z_{k,t} = u_{k,t} - u_{k,t-1}", r"y_{k,t} + z_{k,t} \le 1"],
        "A start or a stop is a change in the on and off state, and a unit cannot do both "
        "in one hour.")},
    "ramps": {"all": (
        "Ramps", [r"P_{k,t} - P_{k,t-1} \le RU_k u_{k,t-1} + SU_k y_{k,t}",
                  r"P_{k,t-1} - P_{k,t} \le RD_k u_{k,t} + SD_k z_{k,t}"],
        "Output can only move by the ramp rate, except at a start or a shut-down.")},
    "minud": {"all": (
        "Minimum up and down times",
        [r"\sum_{\tau = t - UT_k + 1}^{t} y_{k,\tau} \le u_{k,t}",
         r"\sum_{\tau = t - DT_k + 1}^{t} z_{k,\tau} \le 1 - u_{k,t}"],
        "After a start the unit stays on for $UT_k$ hours, and after a stop it stays off for "
        "$DT_k$ hours. Hours already served before $t = 1$ carry in from the initial state.")},
    "battery": {"all": (
        "Battery",
        [r"E_t = E_{t-1} + \eta P^{ch}_t \Delta T - P^{dis}_t \Delta T / \eta",
         r"P^{ch}_t \le \bar{P}^{ch} w_t",
         r"P^{dis}_t \le \bar{P}^{dis} (1 - w_t)",
         r"E_8 \ge E_0"],
        "Stored energy follows charging and discharging with losses. The mode binary $w_t$ "
        "stops it charging and discharging in the same hour. It must finish at least as full "
        "as it started.")},
    "reserve": {"all": (
        "Reserve",
        [r"0 \le r_{k,t} \le RR_k",
         r"r^{B}_t + P^{dis}_t - P^{ch}_t \le \bar{P}^{dis}",
         r"r^{B}_t \Delta T / \eta \le E_t"],
        "Each generator can hold at most its ramp-limited reserve $RR_k$. The battery's reserve "
        "must fit in its power and in its stored energy.")},
    "n1": {"all": (
        "N-1",
        [r"\sum_{j \ne k} r_{j,t} + r^{B}_t \ge P_{k,t} \quad [\pi_{k,t}]"],
        "If generator $k$ trips, everyone else's reserve covers the output it was producing.")},
    "network": {
        "A": ("Flows and ratings",
              [r"f_{\ell,t} = B_\ell \left( \delta_{i(\ell),t} - \delta_{j(\ell),t} \right)",
               r"-\bar{F}_\ell \le f_{\ell,t} \le \bar{F}_\ell"],
              "A DC flow follows the angle difference and stays inside the line rating. Bus 3 is "
              "the reference ($\\delta_{3,t} = 0$). Line 2-3 is rated 800 MW."),
        "B": ("Flows and ratings, Case B",
              [r"f_{\ell,t} = B_\ell \left( \delta_{i(\ell),t} - \delta_{j(\ell),t} \right)",
               r"-\bar{F}_\ell \le f_{\ell,t} \le \bar{F}_\ell"],
              "Same rows as Case A. Only the data change: $\\bar{F}_{23}$ falls from 800 MW to 700 MW."),
    },
}
GROUP_ORDER = ("objective", "balance", "capacity", "logic", "ramps", "minud", "battery",
               "reserve", "n1", "network")


def _variant(group: str, stage: int):
    """Which form of a row group is switched on at this stage, or None if it is absent."""
    if group in ("objective", "logic", "ramps"):
        return "all"
    if group == "balance":
        return "copper" if stage <= 2 else "battery" if stage <= 4 else "network"
    if group == "capacity":
        return "plain" if stage <= 3 else "reserve"
    if group == "minud":
        return "all" if stage >= 2 else None
    if group == "battery":
        return "all" if stage >= 3 else None
    if group in ("reserve", "n1"):
        return "all" if stage >= 4 else None
    return {5: "A", 6: "B"}.get(stage)  # network


def rows_for(stage: int, added_only: bool) -> list:
    """(title, [LaTeX], meaning) for every row group on at this stage, or new at it."""
    out = []
    for group in GROUP_ORDER:
        variant = _variant(group, stage)
        if variant is None:
            continue
        if added_only and stage > 1 and variant == _variant(group, stage - 1):
            continue
        out.append(VARIANTS[group][variant])
    return out


# --- Charts -----------------------------------------------------------------

UNIT_STYLE = {  # fill, hatch: the hatch tells the units apart without colour
    "G1": (ed.NAVY, ""), "G2": (ed.PURPLE, "/"), "G3": (ed.LAVENDER, "x"), "G4": (ed.MUTED, "."),
}


def _pattern(colour, shape):
    return dict(color=colour, line=dict(color=ed.NAVY, width=1.5),
                pattern=dict(shape=shape, fgcolor=ed.NAVY, bgcolor=colour, size=8))


def _layout(fig, title, height=460, legend=True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=ed.NAVY)),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=14, color=ed.NAVY), orientation="h", y=-0.22),
        height=height, margin=dict(t=60, b=40, l=40, r=40), showlegend=legend,
    )


def _axes(fig, xtitle, ytitle):
    fig.update_xaxes(title=dict(text=xtitle, font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.SILVER)
    fig.update_yaxes(title=dict(text=ytitle, font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.NAVY)


def _dispatch_figure(v: dict) -> go.Figure:
    fig = go.Figure()
    for k in UNITS:
        colour, shape = UNIT_STYLE[k]
        fig.add_trace(go.Bar(x=list(HOURS), y=v["P"][k], name=UNIT_NAMES[k],
                             marker=_pattern(colour, shape)))
    fig.add_trace(go.Bar(x=list(HOURS), y=v["Pd"], name="Battery discharge",
                         marker=_pattern(ed.LIMESTONE, "+")))
    fig.add_trace(go.Bar(x=list(HOURS), y=[-p for p in v["Pc"]], name="Battery charging (below zero)",
                         marker=_pattern(ed.LIMESTONE, "-")))
    demand = data()["D"]
    fig.add_trace(go.Scatter(x=list(HOURS), y=demand, mode="lines+markers", name="Demand D<sub>t</sub>",
                             line=dict(color=ed.NAVY, width=4),
                             marker=dict(size=12, symbol="diamond", color="#FFFFFF",
                                         line=dict(color=ed.NAVY, width=3))))
    fig.update_layout(barmode="relative", bargap=0.25)
    fig.update_xaxes(dtick=1)
    _axes(fig, "hour t", "output (MW)")
    _layout(fig, "Dispatch P<sub>k,t</sub> by hour", height=480)
    return fig


def _waterfall(results: dict, stage: int, hbh_total: float | None) -> go.Figure:
    labels = []
    for s in STAGES:
        tick = f"{s['n']}<br>{_short(s['n'])}"
        labels.append(tick + ("<br><b>current stage</b>" if s["n"] == stage else ""))
    fig = go.Figure()
    for key, name, colour, shape in (("energy", "Energy", ed.NAVY, ""),
                                     ("noload", "No-load", ed.PURPLE, "/"),
                                     ("startup", "Start-up", ed.LAVENDER, "x")):
        fig.add_trace(go.Bar(x=labels, y=[results[s["n"]]["costs"][key] for s in STAGES],
                             name=name, marker=_pattern(colour, shape)))
    totals = [results[s["n"]]["costs"]["total"] for s in STAGES]
    fig.add_trace(go.Scatter(x=labels, y=totals, mode="text", showlegend=False, hoverinfo="skip",
                             text=[f"<b>${v:,.0f}</b>" for v in totals], textposition="top center",
                             textfont=dict(size=16, color=ed.NAVY)))
    cur = stage - 1
    fig.add_shape(type="rect", xref="x", yref="y", x0=cur - 0.46, x1=cur + 0.46, y0=0,
                  y1=totals[cur] * 1.13, line=dict(color=ed.PURPLE, width=4, dash="dash"))
    if hbh_total is not None:
        fig.add_trace(go.Scatter(
            x=[labels[0]], y=[hbh_total], mode="markers+text", showlegend=False, hoverinfo="skip",
            marker=dict(symbol="line-ew-open", size=46, line=dict(color=ed.NAVY, width=4)),
            text=[f"hour by hour: ${hbh_total:,.0f} (+${hbh_total - totals[0]:,.0f})"],
            textposition="middle right", textfont=dict(size=16, color=ed.NAVY)))
    fig.update_layout(barmode="stack", bargap=0.35)
    _axes(fig, "", "cost over eight hours ($)")
    fig.update_yaxes(range=[0, max(totals) * 1.25], tickformat=",")
    _layout(fig, "Cost of each stage", height=500)
    return fig


def _short(n: int) -> str:
    return {1: "UC", 2: "+ min up/down", 3: "+ battery", 4: "SCUC", 5: "NCUC A", 6: "NCUC B"}[n]


def _trip_figure(t: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["Output lost"], y=[t["lost"]], marker=_pattern(ed.NAVY, ""),
                         text=[f"{_n(t['lost'])} MW"], textposition="outside",
                         textfont=dict(size=16, color=ed.NAVY), showlegend=False))
    fig.add_trace(go.Bar(x=["Available within 10 minutes"], y=[t["available"]],
                         marker=_pattern(ed.PURPLE, "/"), text=[f"{_n(t['available'])} MW"],
                         textposition="outside", textfont=dict(size=16, color=ed.NAVY),
                         showlegend=False))
    top = max(t["lost"], t["available"], 1.0)
    fig.update_yaxes(range=[0, top * 1.25])
    _axes(fig, "", "MW")
    _layout(fig, "Lost against available", height=340, legend=False)
    return fig


# Three-bus diagram, drawn as network_prices draws its networks.
POS = {1: (0.0, 0.0), 2: (5.0, 0.0), 3: (2.5, 3.6)}
TAGS = {1: (-2.6, 0.75), 2: (5.7, 0.25), 3: (3.6, 5.1)}  # top of each tag stack
LINE_BUSES = {"1-2": (1, 2), "1-3": (1, 3), "2-3": (2, 3)}


def _draw_line(fig, p0, p1, f, label, colour, width, offset=0.6):
    (x0, y0), (x1, y1) = p0, p1
    fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="skip",
                             line=dict(color=colour, width=width)))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    ux, uy = x1 - x0, y1 - y0
    norm = math.hypot(ux, uy)
    ux, uy = ux / norm, uy / norm
    if f is not None and abs(f) > EPS:
        s = 1 if f > 0 else -1
        fig.add_annotation(x=mx + s * 0.4 * ux, y=my + s * 0.4 * uy,
                           ax=mx - s * 0.4 * ux, ay=my - s * 0.4 * uy,
                           xref="x", yref="y", axref="x", ayref="y", text="",
                           showarrow=True, arrowhead=2, arrowsize=1.8,
                           arrowwidth=3, arrowcolor=colour)
    fig.add_annotation(x=mx - offset * uy, y=my + offset * ux, text=label, showarrow=False,
                       font=dict(size=17, color=colour), bgcolor="#FFFFFF")


def _draw_bus(fig, x, y, name, price):
    fig.add_trace(go.Scatter(
        x=[x], y=[y], mode="markers+text", text=[f"<b>{name}</b>"], hoverinfo="skip",
        textfont=dict(size=18, color=ed.NAVY),
        marker=dict(size=86, color=ed.LAVENDER, line=dict(color=ed.NAVY, width=3))))
    fig.add_annotation(x=x, y=y - 0.78, text=f"<b>{LAMBDA} = {price:,.2f}</b>",
                       showarrow=False, font=dict(size=20, color=ed.NAVY), bgcolor="#FFFFFF")


def _draw_tag(fig, x, y, text, symbol, colour):
    fig.add_trace(go.Scatter(
        x=[x], y=[y], mode="markers+text", text=[text], textposition="middle right",
        hoverinfo="skip", textfont=dict(size=16, color=ed.NAVY),
        marker=dict(size=18, symbol=symbol, color=colour, line=dict(color=ed.NAVY, width=2))))


def _network_figure(v: dict, lam: dict, t: int, f23: float) -> go.Figure:
    i = t - 1
    d = data(3, f23)
    F = {"1-2": 1500.0, "1-3": 1500.0, "2-3": f23}
    fig = go.Figure()
    for name, (a, b) in LINE_BUSES.items():
        f = v["f"][name][i]
        if abs(f) >= F[name] - EPS:
            _draw_line(fig, POS[a], POS[b], f, f"<b>{abs(f):,.0f} / {F[name]:,.0f} MW, at rating</b>",
                       ed.PURPLE, 8)
        else:
            _draw_line(fig, POS[a], POS[b], f, f"{abs(f):,.0f} / {F[name]:,.0f} MW", ed.NAVY, 4)
    net = v["Pd"][i] - v["Pc"][i]
    bat = "discharging" if net > EPS else "charging" if net < -EPS else "idle"
    tags = {
        1: [(f"G1 {_n(v['P']['G1'][i])} MW", "square", ed.LAVENDER),
            (f"D<sub>1</sub> {_n(d['D1'])} MW", "triangle-down", ed.LIMESTONE)],
        2: [(f"G2 {_n(v['P']['G2'][i])} MW", "square", ed.LAVENDER),
            ("D<sub>2</sub> 0 MW", "triangle-down", ed.LIMESTONE)],
        3: [(f"G3 {_n(v['P']['G3'][i])} MW", "square", ed.LAVENDER),
            (f"G4 {_n(v['P']['G4'][i])} MW", "square", ed.LAVENDER),
            (f"Battery {bat} {_n(abs(net))} MW", "diamond", ed.LAVENDER),
            (f"<b>G3 + G4 + battery {_n(v['P']['G3'][i] + v['P']['G4'][i] + net)} MW</b>",
             "square", ed.LAVENDER),
            (f"D<sub>3</sub> {_n(d['D'][i] - d['D1'])} MW", "triangle-down", ed.LIMESTONE)],
    }
    for bus, (x, y) in POS.items():
        tx, ty = TAGS[bus]
        for n, (text, symbol, colour) in enumerate(tags[bus]):
            _draw_tag(fig, tx, ty - 0.5 * n, text, symbol, colour)
        _draw_bus(fig, x, y, f"Bus {bus}", lam[bus][i])
    fig.update_xaxes(visible=False, range=[-2.8, 8.4])
    fig.update_yaxes(visible=False, range=[-1.4, 5.5], scaleanchor="x", scaleratio=1)
    _layout(fig, f"Hour {t}: flows and nodal prices", height=560, legend=False)
    return fig


# --- Cached solves -----------------------------------------------------------

@st.cache_data(show_spinner=False)
def _stage(stage: int, ut_g3: int) -> dict:
    return solve_stage(stage, 3 if stage == 1 else ut_g3)


@st.cache_data(show_spinner=False)
def _hour_by_hour() -> dict:
    return hour_by_hour_result()


@st.cache_data(show_spinner=False)
def _prices(stage: int, ut_g3: int) -> dict:
    return prices(stage, ut_g3)


@st.cache_data(show_spinner=False)
def _case_b_limit() -> float:
    return max_hour7_demand_case_b()


# --- The page ---------------------------------------------------------------

PANELS = ("Schedule details", "Trip check", "Prices and settlement")
DEFAULTS = {"uc_stage": 1, "uc_hbh": False, "uc_ut_g3": 3, "uc_panel": PANELS[0],
            "uc_trip_hour": 7, "uc_trip_unit": "G1", "uc_net_hour": 7,
            **{f"uc_trip_inc_{n}": True for n in (*UNITS, "BESS")}}


def _step(delta: int) -> None:
    st.session_state["uc_stage"] = min(6, max(1, st.session_state["uc_stage"] + delta))


def _grid_html(v: dict, prev: dict | None) -> str:
    head = "".join(f"<th>t = {t}</th>" for t in HOURS)
    rows = []
    for k in UNITS:
        cells = []
        for i in range(8):
            u = v["u"][k][i]
            mark = (" ▲" if v["y"][k][i] else "") + (" ▼" if v["z"][k][i] else "")
            changed = prev is not None and prev["u"][k][i] != u
            cls = ("uc-on" if u else "uc-off") + (" uc-chg" if changed else "")
            cells.append(f'<td class="{cls}">{u}{mark}{" ●" if changed else ""}</td>')
        rows.append(f"<tr><th>{UNIT_NAMES[k]}</th>{''.join(cells)}</tr>")
    return f'<table class="uc-grid"><tr><th></th>{head}</tr>{"".join(rows)}</table>'


def _css() -> None:
    st.markdown(
        f"""<style>
[data-testid="stMarkdownContainer"] table {{ width: 100%; border-collapse: collapse; }}
[data-testid="stMarkdownContainer"] th, [data-testid="stMarkdownContainer"] td {{
  text-align: center; padding: .45rem .5rem; border-bottom: 1px solid {ed.SILVER};
}}
[data-testid="stMarkdownContainer"] th {{ border-bottom: 2px solid {ed.SILVER}; }}
table.uc-grid td {{ font-size: 1.15rem; font-weight: 700; border: 1px solid {ed.SILVER}; }}
table.uc-grid th:first-child {{ text-align: left; white-space: nowrap; }}
table.uc-grid td.uc-on {{ background: {ed.LAVENDER}; color: {ed.NAVY}; }}
table.uc-grid td.uc-off {{ background: #FFFFFF; color: {ed.MUTED}; font-weight: 400; }}
table.uc-grid td.uc-chg {{ outline: 4px solid {ed.PURPLE}; outline-offset: -4px; }}
</style>""", unsafe_allow_html=True)


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    ss = st.session_state

    ed.header(
        "One unit commitment model, growing in layers",
        "Start with UC and add one set of rows at a time: minimum up and down times, a "
        "battery, reserve with an N-1 rule, then the network. Watch the schedule and the "
        "cost change at each layer.",
    )
    _css()

    # A. The stage stepper.
    stage = st.radio("Stage", [s["n"] for s in STAGES], horizontal=True, key="uc_stage",
                     format_func=lambda n: f"{n}. {STAGES[n - 1]['label']}")
    c_prev, c_next, c_knob = st.columns([1, 1, 3])
    c_prev.button("Previous", key="uc_prev", width="stretch", on_click=_step, args=(-1,),
                  disabled=stage == 1)
    c_next.button("Next layer", key="uc_next", width="stretch", on_click=_step, args=(1,),
                  disabled=stage == 6)
    c_knob.slider(r"G3 minimum up time $UT_{G3}$ (h)", 1, 4, key="uc_ut_g3", disabled=stage == 1)
    if stage == 1:
        c_knob.caption("Stage 1 has no minimum up or down time rows, so this slider starts "
                       "to matter at stage 2.")
    ut = int(ss["uc_ut_g3"])
    spec = STAGES[stage - 1]
    st.markdown(f"**Stage {stage}, {spec['label']}.** {spec['adds']}")

    results = {s["n"]: _stage(s["n"], ut) for s in STAGES}
    res = results[stage]
    if not res["ok"]:
        ed.note("**No schedule.** This stage has no feasible commitment.")
        return

    hbh_on = stage == 1 and bool(ss["uc_hbh"])
    hbh = _hour_by_hour() if hbh_on else None
    shown = hbh if hbh_on else res
    v = shown["view"]
    prev = None
    if stage > 1:
        prev = results[stage - 1]["view"]
    elif hbh_on:
        prev = res["view"]  # the look-ahead schedule

    cols = st.columns(4)
    for column, (label, key) in zip(cols, [(r"Total cost (\$)", "total"), (r"Energy (\$)", "energy"),
                                           (r"No-load (\$)", "noload"), (r"Start-up (\$)", "startup")]):
        with column:
            ed.headline(label, f"{shown['costs'][key]:,.0f}")

    # B and C, side by side.
    left, right = st.columns([1, 1])
    with left:
        with st.expander("Rows added in this stage", expanded=True):
            for title, tex, meaning in rows_for(stage, added_only=True):
                st.markdown(f"**{title}.** {meaning}")
                for line in tex:
                    st.latex(line)
        with st.expander("The complete model for this stage", expanded=False):
            for title, tex, _ in rows_for(stage, added_only=False):
                st.markdown(f"**{title}**")
                for line in tex:
                    st.latex(line)
    with right:
        st.markdown(f"**Commitment grid $u_{{k,t}}$**" + (" (hour by hour)" if hbh_on else ""))
        st.markdown(_grid_html(v, prev), unsafe_allow_html=True)
        compare = ("the look-ahead stage 1 schedule" if stage == 1
                   else f"stage {stage - 1}")
        st.caption(rf"1 is on and 0 is off. ▲ marks a start ($y_{{k,t}} = 1$) and ▼ a shut-down "
                   rf"($z_{{k,t}} = 1$). A cell with a purple outline and a ● changed from {compare}.")

    # D. Dispatch.
    st.plotly_chart(_dispatch_figure(v), width="stretch")

    # E and F. Cost across all six stages, with the hour-by-hour knob beside it.
    chart, side = st.columns([3, 1])
    with chart:
        st.plotly_chart(_waterfall(results, stage, hbh["costs"]["total"] if hbh_on else None),
                        width="stretch")
        st.markdown("Each stage adds rows. Adding rows can only raise the cost; only a new "
                    "resource, the battery, lowered it.")
    with side:
        st.toggle("Choose each hour on its own (no look-ahead)", key="uc_hbh", disabled=stage != 1)
        if stage != 1:
            st.caption("This toggle works on stage 1 only.")
        elif hbh_on:
            ahead = res["costs"]["total"]
            st.markdown(rf"Hour by hour costs \${hbh['costs']['total']:,.0f}, which is "
                        rf"\${hbh['costs']['total'] - ahead:,.0f} more than looking ahead "
                        rf"(\${ahead:,.0f}). It runs G4 in hours 6 and 7 instead of starting G3 "
                        "early, because each hour ignores the hours after it.")
        else:
            st.caption("Switch it on to see each hour decided on its own, with no look-ahead.")

    # H, I and the schedule tables, one panel at a time.
    panel = st.radio("Panel", PANELS, horizontal=True, key="uc_panel")
    if panel == PANELS[0]:
        _details_panel(v, stage)
    elif panel == PANELS[1]:
        _trip_panel(v, stage)
    else:
        _prices_panel(stage, ut)

    st.caption("Why the battery needs the mode binary $w_t$ is the Topic 6 battery opportunity "
               "cost experiment.")


def _details_panel(v: dict, stage: int) -> None:
    st.subheader("Schedule details")
    head = [""] + [f"t = {t}" for t in HOURS]
    rows = [[rf"$P_{{{k},t}}$ (MW)"] + [_n(p) for p in v["P"][k]] for k in UNITS]
    if stage >= 3 or any(v["Pd"]) or any(v["Pc"]):
        rows.append([r"Battery net output $P^{dis}_t - P^{ch}_t$ (MW)"]
                    + [_n(a - b) for a, b in zip(v["Pd"], v["Pc"])])
        rows.append([r"Stored energy $E_t$ (MWh)"] + [_n(e) for e in v["E"]])
    if stage >= 4:
        rows += [[rf"Reserve $r_{{{k},t}}$ (MW)"] + [_n(r) for r in v["r"][k]] for k in UNITS]
        rows.append([r"Battery reserve $r^{B}_t$ (MW)"] + [_n(r) for r in v["rB"]])
    st.markdown(_pipe_table(head, rows))
    if stage >= 4:
        st.caption("Reserve is what the solver chose to schedule. Several equal-cost choices "
                   "exist, so it can differ between solvers.")


def _trip_panel(v: dict, stage: int) -> None:
    st.subheader("Trip a unit")
    c1, c2 = st.columns(2)
    with c1:
        hour = st.radio("Hour", list(HOURS), horizontal=True, key="uc_trip_hour")
    with c2:
        unit = st.radio("Unit to trip", list(UNITS), horizontal=True, key="uc_trip_unit")
    survivors = [j for j in UNITS if j != unit] + (["BESS"] if stage >= 3 else [])
    st.markdown("**What-if.** Untick a survivor to take it out of the count.")
    include = {}
    for column, name in zip(st.columns(5), (*UNITS, "BESS")):
        usable = name in survivors
        label = "Battery" if name == "BESS" else name
        include[name] = column.checkbox(label, key=f"uc_trip_inc_{name}", disabled=not usable)
    t = trip(v, stage, hour, unit, include)
    if not t["committed"]:
        ed.note(f"**{unit} is not committed in hour {hour}, so nothing is lost.** Pick a "
                "committed unit or another hour.")
        return
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(_trip_figure(t), width="stretch")
    with right:
        rows = []
        for row in t["rows"]:
            name = "Battery" if row["name"] == "BESS" else row["name"]
            if row["name"] == "BESS":
                state = "in use" if row["included"] else "unticked"
                sched = rf"net output {_n(row['scheduled'])} MW"
            else:
                state = ("unticked" if not row["included"] else
                         "committed" if row["committed"] else "not committed")
                sched = f"{_n(row['scheduled'])} MW" if row["committed"] else "off"
            rows.append([name, state, sched, _n(row["capability"]), _n(row["contribution"])])
        st.markdown(_pipe_table(["Survivor", "Status", "Scheduled", "Capability (MW)",
                                 "Counted (MW)"], rows))
    if t["ok"]:
        st.markdown(f"**Pass.** Losing {unit} in hour {hour} removes {_n(t['lost'])} MW, and the "
                    f"survivors can deliver {_n(t['available'])} MW within 10 minutes.")
    else:
        st.markdown(f"**Fail.** Losing {unit} in hour {hour} removes {_n(t['lost'])} MW, but the "
                    f"survivors can deliver only {_n(t['available'])} MW within 10 minutes, "
                    f"short by {_n(t['shortfall'])} MW.")
    caption = ("Each survivor counts at its capability, not at the reserve $r_{j,t}$ the solver "
               r"scheduled: a committed generator gives $\min(RR_j, \bar{P}_j - P_{j,t})$, an "
               "uncommitted one gives 0, and the battery gives the least of its discharge "
               r"headroom and $\eta E_t$.")
    if stage >= 4:
        g1 = v["r"]["G1"][1]
        cap = min(450.0, 1500.0 - v["P"]["G1"][1])
        caption += (rf" In hour 2, G1's capability is {_n(cap)} MW; this solve scheduled "
                    rf"$r_{{G1,2}} = {_n(g1)}$ MW.")
    st.caption(caption)


def _prices_panel(stage: int, ut: int) -> None:
    if stage < 5:
        ed.note("**Prices need the network.** Choose stage 5 or 6 to see nodal prices, "
                "the pricing run and the settlement.")
        return
    res = _stage(stage, ut)
    v = res["view"]
    p = _prices(stage, ut)
    if not p["ok"]:
        ed.note("**No prices.** The pricing run did not solve.")
        return
    case = "Case A" if stage == 5 else "Case B"
    f23 = STAGES[stage - 1]["f23"]
    hour = st.radio("Hour shown in the diagram", list(HOURS), horizontal=True, key="uc_net_hour")
    st.plotly_chart(_network_figure(v, p["lam"], hour, f23), width="stretch")
    st.caption("Arrows point the way the power actually flows. A thick purple line is at its "
               "rating and is labelled \"at rating\". Bus 3 is the reference.")
    i = hour - 1
    rows = []
    for name, (a, b) in LINE_BUSES.items():
        f = v["f"][name][i]
        F = f23 if name == "2-3" else 1500.0
        rows.append([name, f"{a} to {b}", _n(f), _n(F),
                     "at rating" if abs(f) >= F - EPS else "below rating"])
    st.markdown(_pipe_table(["Line", "From to", r"$f_{\ell,t}$ (MW)", r"$\bar{F}_\ell$ (MW)",
                             "Status"], rows))
    if stage == 6:
        limit = _case_b_limit()
        ed.note(f"With line 2-3 at 700 MW the SCUC schedule cannot be dispatched: in hour 7 the "
                f"network and the N-1 rows allow only {_sp(limit)} MW against "
                f"{_sp(data()['D'][6])} MW of demand, so G4 must start again.")

    st.subheader(f"Pricing run, {case}" if stage == 5 else "Case B prices")
    st.markdown(r"Every binary ($u$, $y$, $z$, $w$) is fixed at its MILP value and the remaining "
                r"LP is re-solved. $\lambda_{i,t}$ is the multiplier on the nodal balance row.")
    rows = [[rf"$\lambda_{{{i_},t}}$ (\$/MWh)"] + [_n(x) for x in p["lam"][i_]] for i_ in (1, 2, 3)]
    st.markdown(_pipe_table([""] + [f"t = {t}" for t in HOURS], rows))
    if stage == 5:
        st.markdown(r"In hours 6 and 7, G3 is marginal at 50 \$/MWh, and each extra MW from G3 "
                    r"needs 1 MW more reserve in case G3 trips; that N-1 row has a multiplier of "
                    r"5 \$/MWh, so $\lambda_3 = 55$.")
        with st.expander("The N-1 multiplier for G3", expanded=False):
            st.markdown(_pipe_table(
                ["Hour", r"$\pi_{G3,t}$ (\$/MWh)"],
                [[str(t), _n(p["n1_g3"][t - 1])] for t in (6, 7)]))

    st.subheader(r"Settlement (\$ over eight hours)")
    s = p["settlement"]
    rows = [[UNIT_NAMES[k], _n(s["gens"][k]["revenue"]), _n(s["gens"][k]["cost"]),
             _n(s["gens"][k]["profit"]), _n(s["gens"][k]["uplift"])] for k in UNITS]
    rows.append(["Battery, net revenue", _n(s["battery"]), "", "", ""])
    st.markdown(_pipe_table(["Unit", r"Revenue at the nodal price (\$)",
                             r"As-offered cost: energy + no-load + start-up (\$)", r"Profit (\$)",
                             r"Uplift $= \max(0, -\text{profit})$ (\$)"], rows))
    st.markdown(_pipe_table(["", r"\$"], [
        [r"Consumers pay $\sum_{i,t} D_{i,t} \lambda_{i,t}$", _n(s["consumers"])],
        ["Congestion rent: consumers pay less generator and battery revenue", _n(s["rent"])],
        ["Total uplift", _n(s["uplift"])],
        ["Total uplift as a share of the schedule cost", f"{100 * s['share']:.1f} %"],
    ]))
    if stage == 5:
        st.caption("G3 and the battery are both at bus 3 and can shift up to 70 MW between hours "
                   "7 and 8 at equal cost. How their combined profit splits between them "
                   "depends on the solver; their sum does not.")
