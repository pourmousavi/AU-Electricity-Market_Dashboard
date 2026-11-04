"""Zero-marginal-cost dispatch (Topic 10).

Two modes, in actual units: MW, MWh, $/MWh and $. Hours are one hour long, so MW
and MWh are numerically equal.

1. Wind in the dispatch. One interval: committed thermal units with minimum
   stable generation and one wind farm with availability Wbar (its UIGF) and an
   offer cW. Minimum stable generation brings zero and negative prices forward,
   and the multiplier on a minimum row is the cost of inflexibility.
2. A day with free fuel. Multi-hour dispatch (Topic 5 multi-period ED with the
   Topic 6 battery rows): solar and wind offer 0 $/MWh, one OCGT, a demand
   response bid, load shedding at the VOLL, no commitment. Who sets the price
   when fuel is free, and how more storage energy can lower the battery's own
   revenue.

Every LP is solved with scipy's HiGHS through linprog. Signs (scipy,
minimisation): eqlin.marginals[i] = d(cost)/d(b_eq[i]). The battery SOE row is
written as the lectures write it (Topic 6),
    E_t = E_{t-1} + eta_ch Pch_t dT - Pdis_t dT / eta_dis      [theta_t],
which scipy receives as E_t - E_{t-1} - eta Pch_t + Pdis_t / eta = 0 (E0 at
t = 0), so theta_t is that row's marginal and v_t = -theta_t.

A price is also reported as the left and right change in optimal cost for a
1 MW change in demand. Several presets sit exactly on points where the marginal
unit changes; there the page shows a range, never one solver multiplier.
Students only move the knobs on each page; every preset is fixed in code.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.optimize import linprog

from experiments._kit import ed

EPS = 1e-6
LAMBDA = ed.LAMBDA
MINUS = "\u2212"

# ---------------------------------------------------------------- presets
# Units are (name, offer c_k $/MWh, minimum MW, maximum MW).
M1_PRESETS = {
    "forum": dict(
        label="Forum Q1: units A and B", D=1100.0,
        units=[("A (coal)", 20.0, 300.0, 800.0), ("B (gas)", 50.0, 200.0, 600.0)],
        W_max=1500, W_default=700, cW_default=-30),
    "lecture": dict(
        label="Lecture: 18:00 windy evening (G1 and G2)", D=2400.0,
        units=[("G1 (CCGT)", 40.0, 600.0, 1500.0), ("G2 (coal)", 20.0, 500.0, 1000.0)],
        W_max=2600, W_default=1600, cW_default=-40),
}

M2_PRESETS = {
    "forum": dict(
        label="Forum: two evening hours",
        data=dict(hours=["18:00", "19:00"], D=[500.0, 500.0], S=[0.0, 0.0], W=[200.0, 200.0],
                  cO=120.0, PO=150.0, cDR=400.0, PDR=[0.0, 200.0], VOLL=23200.0,
                  PB=200.0, EB=190.0, eta=1.0, starts_full=True),
        E_label="Energy in the battery at 18:00 (MWh)", E=(160, 600, 10, 190),
        DR=(200, 600, 50, 400),
        battery="Battery 200 MW, $\\eta^{ch} = \\eta^{dis} = 1$. It starts the evening full "
                "(charged free at midday) and may end empty. The slider sets both its capacity "
                "$\\bar{E}$ and its starting energy."),
    "lecture": dict(
        label="Lecture: 11:00 to 18:00",
        data=dict(hours=["11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
                  D=[800.0, 760.0, 780.0, 860.0, 950.0, 1050.0, 1100.0, 1000.0],
                  S=[1000.0, 1060.0, 1020.0, 900.0, 650.0, 330.0, 80.0, 0.0],
                  W=[250.0, 230.0, 220.0, 230.0, 260.0, 300.0, 330.0, 350.0],
                  cO=110.0, PO=320.0, cDR=300.0, PDR=[150.0] * 8, VOLL=23200.0,
                  PB=400.0, EB=800.0, eta=0.95, starts_full=False),
        E_label="Battery energy capacity $\\bar{E}$ (MWh)", E=(500, 2000, 100, 800),
        DR=(150, 600, 50, 300),
        battery="Battery 400 MW, $\\eta^{ch} = \\eta^{dis} = 0.95$. It starts empty and must "
                "end where it started ($E_T \\ge E_0 = 0$)."),
}


# ======================================================================
# Pure helpers (no Streamlit calls from here down to the charts)
# ======================================================================

def _z(x) -> float:
    """HiGHS round-off and -0.0 off a number students read."""
    x = float(x)
    return 0.0 if abs(x) < 1e-9 else x


def _plain(x):
    """Numpy out, plain floats and lists in, so cached results pickle cleanly."""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_plain(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return _z(x)
    return x


def unique(left, right, tol: float = 1e-4) -> bool:
    """True when the left and right changes in cost agree."""
    return left is not None and right is not None and abs(left - right) <= tol


# --- Mode 1 ---------------------------------------------------------------

def mode1_solve(D, units, Wbar, cW, minimums=True):
    n = len(units)
    c = [u[1] for u in units] + [cW]
    bounds = [((u[2] if minimums else 0.0), u[3]) for u in units] + [(0.0, Wbar)]
    r = linprog(c, A_eq=[[1.0] * (n + 1)], b_eq=[D], bounds=bounds, method="highs")
    if r.status != 0:
        return None
    lam = r.eqlin.marginals[0] + 0.0
    P = r.x
    out = dict(lam=lam, cost=r.fun, PW=P[-1], curtailed=Wbar - P[-1], units=[])
    for k, u in enumerate(units):
        lo = bounds[k][0]
        at_lo = P[k] <= lo + EPS
        at_hi = P[k] >= u[3] - EPS
        mu_lo = max(0.0, u[1] - lam) if at_lo else 0.0
        mu_hi = max(0.0, lam - u[1]) if at_hi else 0.0
        out["units"].append(dict(name=u[0], c=u[1], lo=lo, hi=u[3], P=P[k], at_lo=at_lo,
                                 at_hi=at_hi, mu_lo=mu_lo, mu_hi=mu_hi))
    # The wind case of the stationarity table (lecture Part II slide 6). With no
    # wind available both of its limits are zero and its row says nothing about lambda.
    if Wbar <= EPS:
        out["case"] = None
    elif P[-1] >= Wbar - EPS:
        out["case"] = "A"
    elif P[-1] <= EPS:
        out["case"] = "C"
    else:
        out["case"] = "B"
    lo_r = linprog(c, A_eq=[[1.0] * (n + 1)], b_eq=[D - 1], bounds=bounds, method="highs")
    hi_r = linprog(c, A_eq=[[1.0] * (n + 1)], b_eq=[D + 1], bounds=bounds, method="highs")
    out["lam_left"] = r.fun - lo_r.fun if lo_r.status == 0 else None
    out["lam_right"] = hi_r.fun - r.fun if hi_r.status == 0 else None
    return out


def mode1(preset: str, Wbar: float, cW: float, minimums: bool = True):
    p = M1_PRESETS[preset]
    return _plain(mode1_solve(p["D"], p["units"], float(Wbar), float(cW), minimums))


def mode1_curve(preset: str, cW: float, minimums: bool, step: int = 10) -> list:
    """(Wbar, left, right, curtailed) over the slider range."""
    pts = []
    for W in range(0, M1_PRESETS[preset]["W_max"] + 1, step):
        s = mode1(preset, W, cW, minimums)
        pts.append((float(W), s["lam_left"], s["lam_right"], s["curtailed"]))
    return pts


def curve_steps(pts) -> list:
    """[(price, Wbar where it stops holding or None)] read from a curve."""
    steps = []
    for W, left, right, _ in pts:
        if unique(left, right):
            if not steps or abs(steps[-1][0] - left) > 1e-4:
                if steps and steps[-1][1] is None:
                    steps[-1] = (steps[-1][0], W)
                steps.append((left, None))
        elif steps and steps[-1][1] is None:
            steps[-1] = (steps[-1][0], W)
    return steps


# --- Mode 2 ---------------------------------------------------------------

def mode2_solve(hours, D, S, W, cO, PO, cDR, PDR, VOLL, PB, EB, eta, starts_full):
    T = len(hours)
    E0 = EB if starts_full else 0.0
    # Variable layout per hour: S, W, O, DR, L, ch, dis, E (8 per hour).
    nv = 8 * T

    def idx(t, j):
        return 8 * t + j

    c = np.zeros(nv)
    bounds = []
    for t in range(T):
        c[idx(t, 2)] = cO
        c[idx(t, 3)] = cDR
        c[idx(t, 4)] = VOLL
        bounds += [(0, S[t]), (0, W[t]), (0, PO), (0, PDR[t]), (0, None), (0, PB), (0, PB),
                   (0, EB)]
    Aeq, beq = [], []
    for t in range(T):  # balance rows first: t = 0..T-1
        row = np.zeros(nv)
        for j in (0, 1, 2, 3, 4, 6):
            row[idx(t, j)] = 1.0
        row[idx(t, 5)] = -1.0
        Aeq.append(row)
        beq.append(D[t])
    for t in range(T):  # SOE rows: E_t - E_{t-1} - eta ch + dis/eta = 0 (E0 at t = 0)
        row = np.zeros(nv)
        row[idx(t, 7)] = 1.0
        if t > 0:
            row[idx(t - 1, 7)] = -1.0
        row[idx(t, 5)] = -eta
        row[idx(t, 6)] = 1.0 / eta
        Aeq.append(row)
        beq.append(E0 if t == 0 else 0.0)
    Aub, bub = [], []
    if not starts_full:  # end where it started: E_T >= E0 written -E_T <= -E0
        row = np.zeros(nv)
        row[idx(T - 1, 7)] = -1.0
        Aub.append(row)
        bub.append(-E0)

    def run(Dv):
        b = list(Dv) + beq[T:]
        return linprog(c, A_ub=Aub or None, b_ub=bub or None, A_eq=np.array(Aeq), b_eq=b,
                       bounds=bounds, method="highs")

    r = run(D)
    x = r.x

    def g(j):
        return [x[idx(t, j)] for t in range(T)]

    lam = [r.eqlin.marginals[t] + 0.0 for t in range(T)]
    v = [-r.eqlin.marginals[T + t] + 0.0 for t in range(T)]
    res = dict(hours=hours, lam=lam, v=v, cost=r.fun, S=g(0), W=g(1), O=g(2), DR=g(3), L=g(4),
               ch=g(5), dis=g(6), E=g(7))
    res["curt_S"] = [S[t] - res["S"][t] for t in range(T)]
    res["curt_W"] = [W[t] - res["W"][t] for t in range(T)]
    # Left and right prices and price-setter labels from +-1 MW demand perturbations.
    left, right, setter = [], [], []
    names = ["solar (curtailed)", "wind (curtailed)", "OCGT", "demand response",
             "load shedding (VOLL)", "battery (charging)", "battery (discharging)"]
    for t in range(T):
        Dm = list(D)
        Dm[t] -= 1
        Dp = list(D)
        Dp[t] += 1
        rm, rp = run(Dm), run(Dp)
        left.append(r.fun - rm.fun)
        right.append(rp.fun - r.fun)
        if abs(left[-1] - right[-1]) > 1e-4:
            setter.append("changes here (price is a range)")
            continue
        dx = rp.x - x
        moves = [(abs(dx[idx(t, j)]), j) for j in range(7)]
        _, j = max(moves)
        name = names[j]
        if j in (5, 6):
            # The battery moved energy out of (or into) another hour: name what replaced it there.
            other = [(abs(dx[idx(tt, jj)]), tt, jj) for tt in range(T) if tt != t
                     for jj in range(5)]
            m2, tt, jj = max(other) if other else (0.0, None, None)
            if m2 > EPS:
                name = "battery at its opportunity cost (displaces %s at %s)" % (
                    names[jj].replace(" (curtailed)", ""), hours[tt])
            else:
                name = "battery at its opportunity cost"
        setter.append(name)
    res["lam_left"], res["lam_right"], res["setter"] = left, right, setter
    res["rev_battery"] = sum(lam[t] * (res["dis"][t] - res["ch"][t]) for t in range(T))
    res["avg_price"] = sum(lam) / T
    mwh_s, mwh_w = sum(res["S"]), sum(res["W"])
    res["capture_solar"] = (sum(lam[t] * res["S"][t] for t in range(T)) / mwh_s
                            if mwh_s > EPS else None)
    res["capture_wind"] = (sum(lam[t] * res["W"][t] for t in range(T)) / mwh_w
                           if mwh_w > EPS else None)
    res["margin_ocgt"] = sum((lam[t] - cO) * res["O"][t] for t in range(T))
    return res


def mode2(preset: str, EB: float | None = None, cDR: float | None = None) -> dict:
    p = dict(M2_PRESETS[preset]["data"])
    if EB is not None:
        p["EB"] = float(EB)
    if cDR is not None:
        p["cDR"] = float(cDR)
    return _plain(mode2_solve(**p))


def mode2_sweep(preset: str, cDR: float) -> list:
    """(battery energy, net revenue, total cost) over the slider range at the slider step."""
    lo, hi, step, _ = M2_PRESETS[preset]["E"]
    out = []
    for EB in range(lo, hi + 1, step):
        s = mode2(preset, EB, cDR)
        out.append((float(EB), s["rev_battery"], s["cost"]))
    return out


# --- Formatting -------------------------------------------------------------

def _n(x: float, dp: int = 2) -> str:
    """Up to dp decimals, no trailing zeros, no thousands separator, Unicode minus."""
    s = f"{round(float(x), dp) + 0.0:.{dp}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace("-", MINUS)


def _p(x: float) -> str:
    """A negative number in brackets, for substituting into an expression."""
    return f"({_n(x)})" if round(x, 2) < 0 else _n(x)


def usd(x: float) -> str:
    """Dollar first, no separators: $76000."""
    return (MINUS if round(x) < 0 else "") + f"${abs(round(x)):.0f}"


def _md_usd(x: float) -> str:
    """usd() for markdown, where a bare $ opens maths."""
    return usd(x).replace("$", r"\$")


def price_text(left, right, unit: str = " $/MWh") -> str:
    """'−30 $/MWh' or 'between 20 and 50 $/MWh' under the range rule."""
    if unique(left, right):
        return f"{_n(left)}{unit}"
    if left is not None and right is not None:
        lo, hi = sorted((left, right))
        return f"between {_n(lo)} and {_n(hi)}{unit}"
    if left is not None:
        return f"{_n(left)} or more{unit}"
    return f"up to {_n(right)}{unit}"


RANGE_SENTENCE = ("At exactly this point the marginal unit changes, so the price is not unique. "
                  "Move the slider by one step.")


def _pipe_table(head: list[str], rows: list[list[str]]) -> str:
    """A markdown table, so its cells reach KaTeX."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _short(name: str) -> str:
    return name.split(" (")[0]


def m1_setter_sentence(s: dict) -> str | None:
    """Who sets lambda, from the solution. None when lambda is a range."""
    if not unique(s["lam_left"], s["lam_right"]):
        return None
    if s["case"] == "B":
        return r"Set by the curtailed wind farm: $\lambda = c_W$ (case B)."
    for u in s["units"]:
        if not u["at_lo"] and not u["at_hi"]:
            return f"Set by {_short(u['name'])}'s offer."
    return None


def curve_sentence(on: list, off: list, cW: float) -> str:
    """The caption under the price curve, with the breakpoints read from the two curves."""
    def describe(steps):
        parts = []
        for i, (price, end) in enumerate(steps):
            if end is None:
                if i == 0:
                    return f"{_n(price)} \\$/MWh over the whole range"
                parts.append("then the wind offer" if abs(price - cW) < 1e-4
                             else f"then {_n(price)} \\$/MWh")
            else:
                parts.append(f"{_n(price)} \\$/MWh up to {_n(end)} MW"
                             + (" of wind" if i == 0 else ""))
        return ", ".join(parts)

    text = f"With minimums: {describe(on)}."
    bps_on = [e for _, e in on if e is not None]
    bps_off = [e for _, e in off if e is not None]
    same = [round(p, 4) for p, _ in on] == [round(p, 4) for p, _ in off]
    if same and bps_off:
        joined = " and ".join(_n(b) for b in bps_off)
        text += f" Without minimums the same steps come at {joined} MW"
    else:
        text += f" Without minimums: {describe(off)}"
    if (same and bps_on and bps_off and bps_on[-1] < bps_off[-1]
            and abs(on[-1][0] - cW) < 1e-4):
        what = "the negative price" if cW < 0 else "the wind price"
        text += f": inflexibility brings {what} forward."
    else:
        text += "."
    return text


# ======================================================================
# Charts
# ======================================================================

CHART_FONT = ed.CHART_FONT


def _pattern(colour, shape="", fg=ed.NAVY, line=ed.NAVY):
    return dict(color=colour, line=dict(color=line, width=1.5),
                pattern=dict(shape=shape, fgcolor=fg, bgcolor=colour, size=8))


def _layout(fig, title, height=440, legend=True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=ed.NAVY)),
        font=CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=14, color=ed.NAVY), orientation="h", y=-0.22),
        height=height, margin=dict(t=60, b=40, l=40, r=40), showlegend=legend,
    )


def _axes(fig, xtitle, ytitle):
    fig.update_xaxes(title=dict(text=xtitle, font=CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.SILVER)
    fig.update_yaxes(title=dict(text=ytitle, font=CHART_FONT), tickfont=ed.TICK_FONT,
                     gridcolor=ed.SILVER, zerolinecolor=ed.NAVY)


def _m1_dispatch(s: dict, Wbar: float, minimums: bool) -> go.Figure:
    labels = [f"{u['name']}: {_n(u['P'])} MW" for u in s["units"]]
    labels.append(f"Wind: {_n(s['PW'])} MW")
    mins = [u["lo"] if minimums else 0.0 for u in s["units"]] + [0.0]
    above = [u["P"] - m for u, m in zip(s["units"], mins)] + [s["PW"]]
    spare = [u["hi"] - u["P"] for u in s["units"]] + [0.0]
    curt = [0.0] * len(s["units"]) + [s["curtailed"]]

    def txt(vals, fmt):
        return [fmt(v) if v > EPS else "" for v in vals]

    fig = go.Figure()
    if minimums:
        fig.add_trace(go.Bar(y=labels, x=mins, orientation="h", name="minimum",
                             marker=_pattern(ed.SILVER),
                             text=txt(mins, lambda v: f"minimum {_n(v)} MW"),
                             textposition="inside", insidetextanchor="middle",
                             textfont=dict(size=16, color=ed.NAVY)))
    fig.add_trace(go.Bar(y=labels, x=above, orientation="h",
                         name="output above the minimum" if minimums else "output",
                         marker=_pattern(ed.NAVY),
                         text=txt(above, lambda v: f"{_n(v)} MW"),
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=16, color="#FFFFFF")))
    fig.add_trace(go.Bar(y=labels, x=spare, orientation="h", name="spare capacity",
                         marker=dict(color="#FFFFFF", line=dict(color=ed.NAVY, width=2)),
                         text=txt(spare, lambda v: f"spare {_n(v)} MW"),
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=16, color=ed.NAVY)))
    fig.add_trace(go.Bar(y=labels, x=curt, orientation="h", name="wind curtailed",
                         marker=_pattern(ed.PURPLE, "/", fg="#FFFFFF"),
                         text=txt(curt, lambda v: f"curtailed {_n(v)} MW"),
                         textposition="inside", insidetextanchor="middle",
                         textfont=dict(size=16, color=ed.NAVY)))
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_yaxes(autorange="reversed")
    _axes(fig, "MW", "")
    _layout(fig, "Committed plant at its minimum leaves less room for wind", height=380)
    return fig


def _curve_xy(pts):
    """Step line with vertical risers; a range point is drawn as its riser."""
    xs, ys = [], []
    for W, left, right, _ in pts:
        if unique(left, right):
            xs.append(W)
            ys.append(left)
        else:
            a, b = (left, right) if not ys or abs(ys[-1] - left) < abs(ys[-1] - right) \
                else (right, left)
            xs += [W, W]
            ys += [a, b]
    return xs, ys


def _m1_curve(on, off, Wbar, s, cW, Wmax) -> go.Figure:
    fig = go.Figure()
    curtailed = [i for i, p in enumerate(on) if p[3] > EPS]
    if curtailed:
        x0 = on[curtailed[0] - 1][0] if curtailed[0] > 0 else 0.0
        fig.add_vrect(x0=x0, x1=Wmax, fillcolor=ed.LAVENDER, opacity=1, layer="below",
                      line_width=0, annotation_text="wind curtailed: wind sets the price",
                      annotation_position="top left",
                      annotation_font=dict(size=15, color=ed.NAVY))
    for pts, name, colour, dash in ((on, "minimums enforced", ed.NAVY, "solid"),
                                    (off, "minimums ignored", ed.PURPLE, "dash")):
        xs, ys = _curve_xy(pts)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=name, line_shape="hv",
                                 line=dict(color=colour, width=4, dash=dash)))
    lo, hi = s["lam_left"], s["lam_right"]
    ys = [lo] if unique(lo, hi) else [v for v in (lo, hi) if v is not None]
    fig.add_trace(go.Scatter(
        x=[Wbar] * len(ys), y=ys, mode="markers+text", name="now", showlegend=False,
        marker=dict(size=16, symbol="diamond", color="#FFFFFF", line=dict(color=ed.NAVY, width=3)),
        text=[f"now: {price_text(lo, hi)}"] + [""] * (len(ys) - 1),
        textposition="top right", textfont=dict(size=16, color=ed.NAVY)))
    _axes(fig, "wind availability P̄<sub>W</sub> (MW)", f"price {LAMBDA} ($/MWh)")
    fig.update_xaxes(range=[0, Wmax])
    vals = [y for pts in (on, off) for p in pts for y in p[1:3] if y is not None]
    pad = 0.15 * (max(vals) - min(vals) or 10.0)
    fig.update_yaxes(range=[min(vals) - pad, max(vals) + pad])
    _layout(fig, f"Price against wind availability, wind offer {_n(cW)} $/MWh", height=460)
    return fig


M2_STYLE = {  # key: (legend name, fill, hatch, hatch colour)
    "W": ("wind", ed.NAVY, "", ed.NAVY),
    "S": ("solar", ed.LIMESTONE, ".", ed.NAVY),
    "O": ("OCGT", ed.SILVER, "x", ed.NAVY),
    "DR": ("DR", ed.LAVENDER, "/", ed.NAVY),
    "dis": ("battery discharge", ed.PURPLE, "", ed.PURPLE),
    "L": ("load shed", ed.MUTED, "+", "#FFFFFF"),
}


def _m2_prices(s: dict) -> go.Figure:
    hours = s["hours"]
    base, text = [], []
    for lo, hi in zip(s["lam_left"], s["lam_right"]):
        if unique(lo, hi):
            base.append(lo)
            text.append(_n(lo))
        else:
            base.append(min(lo, hi))
            text.append("")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=hours, y=base, name=f"{LAMBDA}<sub>t</sub>", marker=_pattern(ed.NAVY),
                         text=text, textposition="outside",
                         textfont=dict(size=16, color=ed.NAVY), showlegend=False))
    top = max(max(s["lam_left"]), max(s["lam_right"]), 1.0)
    for h, lo, hi in zip(hours, s["lam_left"], s["lam_right"]):
        if unique(lo, hi):
            continue
        fig.add_trace(go.Scatter(
            x=[h, h], y=sorted((lo, hi)), mode="lines+markers+text", showlegend=False,
            line=dict(color=ed.PURPLE, width=2), marker=dict(symbol="line-ew", size=18,
                                                             line=dict(color=ed.PURPLE, width=3)),
            text=["", f"range {_n(min(lo, hi))} to {_n(max(lo, hi))}"],
            textposition="top center", textfont=dict(size=16, color=ed.NAVY)))
    _axes(fig, "hour", f"{LAMBDA}<sub>t</sub> ($/MWh)")
    fig.update_yaxes(range=[min(0.0, min(s["lam_left"])), top * 1.2])
    _layout(fig, "Price in each hour", height=400, legend=False)
    return fig


def _m2_dispatch(s: dict, D: list) -> go.Figure:
    hours = s["hours"]
    fig = go.Figure()
    for key in ("W", "S", "O", "DR", "dis", "L"):
        vals = s[key]
        if key == "L" and max(vals) <= EPS:
            continue
        name, fill, hatch, fg = M2_STYLE[key]
        fig.add_trace(go.Bar(x=hours, y=vals, name=name, marker=_pattern(fill, hatch, fg)))
    for key, name, hatch in (("curt_W", "wind curtailed", "\\"), ("curt_S", "solar curtailed", "/")):
        vals = s[key]
        if max(vals) <= EPS:
            continue
        fig.add_trace(go.Bar(x=hours, y=vals, name=name,
                             marker=_pattern("#FFFFFF", hatch, fg=ed.PURPLE, line=ed.PURPLE),
                             text=["curtailed" if v > EPS else "" for v in vals],
                             textposition="inside", textfont=dict(size=14, color=ed.NAVY)))
    if max(s["ch"]) > EPS:
        fig.add_trace(go.Bar(x=hours, y=[-v for v in s["ch"]], name="battery charging (below zero)",
                             marker=_pattern(ed.PURPLE, "-", fg="#FFFFFF"),
                             text=["charging" if v > EPS else "" for v in s["ch"]],
                             textposition="inside", textfont=dict(size=14, color="#FFFFFF")))
    fig.add_trace(go.Scatter(x=hours, y=D, mode="markers", name="demand D<sub>t</sub>",
                             marker=dict(size=16, symbol="diamond", color=ed.NAVY,
                                         line=dict(color="#FFFFFF", width=2))))
    fig.update_layout(barmode="relative", bargap=0.25)
    _axes(fig, "hour", "MW")
    _layout(fig, "Dispatch by hour", height=500)
    return fig


def _m2_energy(s: dict, EB: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s["hours"], y=s["E"], mode="lines+markers+text",
                             name="E<sub>t</sub>", line=dict(color=ed.NAVY, width=3),
                             marker=dict(size=10, color=ed.NAVY),
                             text=[_n(e, 1) for e in s["E"]], textposition="top center",
                             textfont=dict(size=14, color=ed.NAVY), showlegend=False))
    fig.add_hline(y=EB, line=dict(color=ed.PURPLE, width=2, dash="dash"),
                  annotation_text=f"Ē = {_n(EB)} MWh", annotation_position="bottom right",
                  annotation_font=dict(size=14, color=ed.NAVY))
    _axes(fig, "end of hour", "stored energy (MWh)")
    fig.update_yaxes(range=[0, EB * 1.2])
    _layout(fig, "Stored energy E<sub>t</sub>", height=300, legend=False)
    return fig


def _m2_sweep(sweep: list, EB: float, current: dict) -> go.Figure:
    xs = [p[0] for p in sweep]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[p[1] for p in sweep], mode="lines+markers",
                             name="battery net revenue", line=dict(color=ed.PURPLE, width=4),
                             marker=dict(size=8, color=ed.PURPLE)))
    fig.add_trace(go.Scatter(x=xs, y=[p[2] for p in sweep], mode="lines", name="total cost",
                             line=dict(color=ed.NAVY, width=3, dash="dash")))
    fig.add_vline(x=EB, line=dict(color=ed.MUTED, width=2, dash="dot"))
    fig.add_trace(go.Scatter(
        x=[EB], y=[current["rev_battery"]], mode="markers+text", showlegend=False,
        marker=dict(size=16, symbol="diamond", color="#FFFFFF", line=dict(color=ed.PURPLE, width=3)),
        text=[f"now: {_n(EB)} MWh, revenue {usd(current['rev_battery'])}"],
        textposition="top right", textfont=dict(size=16, color=ed.NAVY)))
    _axes(fig, "battery energy (MWh)", "$")
    fig.update_yaxes(tickformat="d", rangemode="tozero")
    _layout(fig, "Revenue against battery energy", height=440)
    return fig


# ======================================================================
# Cached wrappers: the arguments are the cache key
# ======================================================================

@st.cache_data(show_spinner=False)
def _m1(preset: str, W: int, cW: int, minimums: bool):
    return mode1(preset, W, cW, minimums)


@st.cache_data(show_spinner=False)
def _m1_pts(preset: str, cW: int, minimums: bool):
    return mode1_curve(preset, cW, minimums)


@st.cache_data(show_spinner=False)
def _m2(preset: str, EB: int, cDR: int):
    return mode2(preset, EB, cDR)


@st.cache_data(show_spinner=False)
def _m2_sw(preset: str, cDR: int):
    return mode2_sweep(preset, cDR)


# ======================================================================
# The page
# ======================================================================

MODES = ("Wind in the dispatch", "A day with free fuel")
MODE_SENTENCES = {
    MODES[0]: "One interval: when the wind farm sets the price, and how the minimum stable "
              "generation of committed plant brings zero and negative prices forward.",
    MODES[1]: "Several hours with free solar and wind: who sets the price when fuel is free, "
              "and how more storage energy can lower the battery's own revenue.",
}
DEFAULTS = {"zm_mode": MODES[0]}


def _save(key: str) -> None:
    st.session_state["zm_keep_" + key[3:]] = st.session_state[key]


def _cb(key: str, then) -> None:
    _save(key)
    if then is not None:
        then()


def _kept(key: str, default, lo=None, hi=None, then=None, options=None) -> dict:
    """Widget kwargs for a widget drawn only inside one mode. Streamlit drops a widget's
    state when it is not drawn, so the value is kept under a shadow key and written back
    into the widget key just before the widget is drawn, clamped to the current range."""
    value = st.session_state.get("zm_keep_" + key[3:], default)
    if options is not None and value not in options:
        value = default
    if lo is not None:
        value = int(min(hi, max(lo, value)))
    st.session_state[key] = value
    return dict(key=key, on_change=_cb, args=(key, then))


def _put(key: str, value) -> None:
    """Set a widget's value and its shadow together (used when a preset changes)."""
    st.session_state[key] = value
    st.session_state["zm_keep_" + key[3:]] = value


def _reset_m1() -> None:
    p = M1_PRESETS[st.session_state["zm_m1_preset"]]
    _put("zm_W", p["W_default"])
    _put("zm_cW", p["cW_default"])
    _put("zm_min", True)


def _reset_m2() -> None:
    p = M2_PRESETS[st.session_state["zm_m2_preset"]]
    _put("zm_EB", p["E"][3])
    _put("zm_DR", p["DR"][3])


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

    ed.header("Zero-marginal-cost dispatch", "Topic 10: who sets the price when fuel is free")
    _css()
    mode = st.radio("Mode", MODES, horizontal=True, key="zm_mode")
    st.markdown(MODE_SENTENCES[mode])
    if mode == MODES[0]:
        _wind_page()
    else:
        _day_page()


# --- Mode 1 -----------------------------------------------------------------

def _wind_page() -> None:
    ss = st.session_state
    st.radio("Preset", list(M1_PRESETS), horizontal=True,
             format_func=lambda k: M1_PRESETS[k]["label"],
             **_kept("zm_m1_preset", "forum", options=list(M1_PRESETS), then=_reset_m1))
    preset = ss["zm_m1_preset"]
    p = M1_PRESETS[preset]

    left, right = st.columns([1, 1.4], gap="large")
    with left:
        rows = [[u[0], _n(u[1]), _n(u[2]), _n(u[3])]
                for u in p["units"]]
        st.markdown(_pipe_table(["Unit", r"$c_k$ (\$/MWh)", r"$\underline{P}_k$ (MW)",
                                 r"$\bar{P}_k$ (MW)"], rows))
        st.markdown(f"Demand $D$ = {_n(p['D'])} MW. One interval; both units are committed.")
    with right:
        W = int(st.slider(r"Wind availability $\bar{P}_W$, its UIGF (MW)", 0, p["W_max"], step=10,
                          **_kept("zm_W", p["W_default"], 0, p["W_max"])))
        cW = int(st.slider(r"Wind offer $c_W$ (\$/MWh)", -100, 20, step=5,
                           **_kept("zm_cW", p["cW_default"], -100, 20)))
        minimums = bool(st.toggle(r"Enforce minimum stable generation $\underline{P}_k$",
                                  **_kept("zm_min", True)))

    with st.expander("The LP and its multipliers", expanded=True):
        st.latex(r"\min \sum_{k} c_k P_k + c_W P_W")
        st.latex(r"\sum_{k} P_k + P_W = D \quad [\lambda]")
        st.latex(r"\underline{P}_k \le P_k \le \bar{P}_k \quad [\underline{\mu}_k, \bar{\mu}_k]")
        st.latex(r"0 \le P_W \le \bar{P}_W \quad [\underline{\mu}_W, \bar{\mu}_W]")
        st.latex(r"C_W = \bar{P}_W - P_W")
        st.markdown("Stationarity for the wind farm and for each thermal unit:")
        st.latex(r"\lambda = c_W + \bar{\mu}_W - \underline{\mu}_W, \qquad "
                 r"\lambda = c_k + \bar{\mu}_k - \underline{\mu}_k")

    s = _m1(preset, W, cW, minimums)
    rng = (s["lam_left"], s["lam_right"])
    is_unique = unique(*rng)

    # A. The price.
    st.subheader("The price")
    ed.headline(r"Price $\lambda$", price_text(*rng))
    sentence = m1_setter_sentence(s)
    if not is_unique:
        st.markdown(RANGE_SENTENCE)
    elif sentence:
        st.markdown(sentence)
    st.markdown(f"Wind dispatched {_n(s['PW'])} MW, curtailed {_n(s['curtailed'])} MW.")

    # B. Dispatch.
    st.plotly_chart(_m1_dispatch(s, W, minimums), width="stretch")
    st.caption("Grey is the minimum each committed unit must produce, navy is output, a white "
               "bar with a navy outline is spare capacity, and purple with a diagonal hatch is "
               "curtailed wind.")

    # C. Price against wind availability.
    on, off = _m1_pts(preset, cW, True), _m1_pts(preset, cW, False)
    st.plotly_chart(_m1_curve(on, off, W, s, cW, p["W_max"]), width="stretch")
    st.caption(curve_sentence(curve_steps(on), curve_steps(off), cW))

    # D. Stationarity, with the numbers.
    st.subheader("Stationarity, with the numbers")
    cases = [
        ("A", r"All available wind used, $P_W = \bar{P}_W$: $\lambda \ge c_W$."),
        ("B", r"Partly curtailed, $0 < P_W < \bar{P}_W$: $\lambda = c_W$."),
        ("C", r"Fully curtailed, $P_W = 0$: $\lambda \le c_W$."),
    ]
    for case, text in cases:
        now = s["case"] == case
        ed.row(f"**Case {case}.** {text}" + (" **← now**" if now else ""), marginal=now)
    if s["case"] is None:
        st.markdown(r"No wind is available, so both of its limits are zero and its row says "
                    r"nothing about $\lambda$.")

    rows = []
    for u in s["units"]:
        name = _short(u["name"])
        lo_word = "at its minimum" if minimums else "at zero, its lower limit"
        if u["at_lo"]:
            pos = lo_word
        elif u["at_hi"]:
            pos = "at its maximum"
        else:
            pos = "between its limits"
        if not is_unique and (u["at_lo"] or u["at_hi"]):
            mult = r"not unique while $\lambda$ is a range"
        elif u["at_lo"]:
            mult = (rf"$\underline{{\mu}}_{{{name}}} = c_{{{name}}} - \lambda$ = "
                    f"{_n(u['c'])} {MINUS} {_p(s['lam'])} = {_n(u['mu_lo'])}")
        elif u["at_hi"]:
            mult = (rf"$\bar{{\mu}}_{{{name}}} = \lambda - c_{{{name}}}$ = "
                    f"{_p(s['lam'])} {MINUS} {_n(u['c'])} = {_n(u['mu_hi'])}")
        else:
            mult = "0 (both multipliers)"
        rows.append([name, _n(u["P"]), pos, mult])
    st.markdown(_pipe_table(["Unit", r"$P_k$ (MW)", "Position", r"Multiplier (\$/MWh)"], rows))
    st.caption("The multiplier on a minimum row is the cost of inflexibility: what the system "
               "would save if that unit could go 1 MW lower.")


# --- Mode 2 -----------------------------------------------------------------

def _day_page() -> None:
    ss = st.session_state
    st.radio("Preset", list(M2_PRESETS), horizontal=True,
             format_func=lambda k: M2_PRESETS[k]["label"],
             **_kept("zm_m2_preset", "forum", options=list(M2_PRESETS), then=_reset_m2))
    preset = ss["zm_m2_preset"]
    p = M2_PRESETS[preset]
    d = p["data"]

    left, right = st.columns([1.4, 1], gap="large")
    with left:
        head = ["Hour"] + d["hours"]
        rows = [[r"Demand $D_t$ (MW)"] + [_n(x) for x in d["D"]],
                ["Solar available (MW)"] + [_n(x) for x in d["S"]],
                ["Wind available (MW)"] + [_n(x) for x in d["W"]],
                ["Demand response available (MW)"] + [_n(x) for x in d["PDR"]]]
        st.markdown(_pipe_table(head, rows))
        st.markdown(f"Solar and wind offer 0 \\$/MWh. OCGT {_n(d['cO'])} \\$/MWh, 0 to "
                    f"{_n(d['PO'])} MW. Load shedding at a VOLL of {_n(d['VOLL'])} \\$/MWh, the "
                    f"market price cap. {p['battery']}")
    with right:
        lo, hi, step, default = p["E"]
        EB = int(st.slider(p["E_label"], lo, hi, step=step, **_kept("zm_EB", default, lo, hi)))
        lo, hi, step, default = p["DR"]
        cDR = int(st.slider(r"Demand response bid (\$/MWh)", lo, hi, step=step,
                            **_kept("zm_DR", default, lo, hi)))

    with st.expander("The LP and its multipliers", expanded=False):
        st.latex(r"\min \sum_{t} \left( c_O P^{O}_t + c_{DR} P^{DR}_t + \text{VOLL}\, L_t \right)")
        st.latex(r"P^{S}_t + P^{W}_t + P^{O}_t + P^{DR}_t + L_t + P^{dis}_t - P^{ch}_t = D_t "
                 r"\quad [\lambda_t]")
        st.latex(r"E_t = E_{t-1} + \eta^{ch} P^{ch}_t \Delta T - P^{dis}_t \Delta T / \eta^{dis} "
                 r"\quad [\theta_t]")
        st.latex(r"0 \le P^{S}_t \le \bar{P}^{S}_t, \quad 0 \le P^{W}_t \le \bar{P}^{W}_t, \quad "
                 r"0 \le P^{O}_t \le \bar{P}^{O}, \quad 0 \le P^{DR}_t \le \bar{P}^{DR}_t")
        st.latex(r"0 \le P^{ch}_t, P^{dis}_t \le \bar{P}, \quad 0 \le E_t \le \bar{E}")
        st.markdown(r"The value of stored energy is $v_t = -\theta_t$ (Topic 6). When the "
                    r"battery is marginal it sets $\lambda_t$ at its opportunity cost: what a MWh "
                    r"would earn in another hour.")

    s = _m2(preset, EB, cDR)
    ranges = [not unique(lo, hi) for lo, hi in zip(s["lam_left"], s["lam_right"])]

    # A. Prices and who sets them.
    st.subheader("Prices and who sets them")
    st.plotly_chart(_m2_prices(s), width="stretch")
    rows = []
    for t, h in enumerate(s["hours"]):
        lam = price_text(s["lam_left"][t], s["lam_right"][t], unit="")
        v = "not unique" if ranges[t] else _n(s["v"][t])
        rows.append([h, lam, s["setter"][t], v])
    st.markdown(_pipe_table(["Hour", r"$\lambda_t$ (\$/MWh)", "Who sets it",
                             r"$v_t$ (\$/MWh)"], rows))
    if any(ranges):
        st.markdown(RANGE_SENTENCE)
    st.caption("When fuel is free, the price is set by curtailed renewables at their offer, by "
               "the OCGT or demand response at their offers, by scarcity at the VOLL, or by the "
               "battery at its opportunity cost.")

    # B. Dispatch by hour.
    st.subheader("Dispatch by hour")
    st.plotly_chart(_m2_dispatch(s, d["D"]), width="stretch")
    st.plotly_chart(_m2_energy(s, float(EB)), width="stretch")

    # C. The battery's account.
    st.subheader("The battery's account")
    c1, c2, c3 = st.columns(3)
    with c1:
        ed.headline(r"Battery net revenue $\sum_t \lambda_t (P^{dis}_t - P^{ch}_t)$",
                    usd(s["rev_battery"]))
    with c2:
        ed.headline("Total cost", usd(s["cost"]))
    with c3:
        ed.headline(r"OCGT margin $\sum_t (\lambda_t - c_O) P^{O}_t$", usd(s["margin_ocgt"]))
    st.latex(r"\bar{\lambda}^{cap} = \frac{\sum_t \lambda_t P_t}{\sum_t P_t}, \qquad "
             r"\text{time-weighted average} = \frac{1}{T} \sum_t \lambda_t")
    rows = []
    if s["capture_solar"] is not None:
        rows.append(["Solar capture price", _n(s["capture_solar"])])
    if s["capture_wind"] is not None:
        rows.append(["Wind capture price", _n(s["capture_wind"])])
    rows.append(["Time-weighted average price", _n(s["avg_price"])])
    st.markdown(_pipe_table(["", r"\$/MWh"], rows))
    if any(ranges):
        st.markdown("At this energy some prices are a range, so these money figures use the "
                    "price the solver reports, one end of each range.")
    st.caption("Each solar farm lowers the price in exactly the hours it produces.")

    # D. Revenue against battery energy.
    st.plotly_chart(_m2_sweep(_m2_sw(preset, cDR), float(EB), s), width="stretch")
    st.caption("More storage removes the scarcity that pays for it. Once the battery no longer "
               "has to ration its energy across hours, its price, and its revenue, fall.")
