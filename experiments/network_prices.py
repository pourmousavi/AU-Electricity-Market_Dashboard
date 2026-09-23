"""Where the nodal price comes from (Topic 7).

Two modes. Network mode solves a fixed single-sided DC OPF on one of two
networks and lets students check every price against the three stationarity
rules. Losses mode is the Part V two-node system with L = K f^2, solved either
with the losses inside the balance or NEMDE style with a static MLF.

Everything is in actual units: MW, $/MWh, $/h, ohms, MW/rad. The networks,
reactances, offers and capacities are constants here; students only move the
ratings, the switchable lines, the demands and, in Losses mode, K and G2's
offer. Deliberately self-contained: the legacy _kit/dc_network page is per unit
and double-sided and uses different notation.

Sign convention, exactly as the lectures write it. Bus rows
sum P_k - D_i - sum_out f + sum_in f = 0 carry lambda_i, flow rows
f_l - B_l delta_from + B_l delta_to = 0 carry rho_l, and the rating and
capacity limits are variable bounds. Scipy's marginals are d(objective)/d(rhs),
so lambda and rho come straight off eqlin; an upper-bound marginal is negative
when binding, so sigma-bar = -upper and mu-bar = -upper.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.optimize import linprog, minimize_scalar

from experiments._kit import ed

EPS = 1e-6
V = 330.0  # kV
X = 21.78  # ohms, every line
B = V ** 2 / X  # MW/rad, 5000
GENS = ed.GENERATORS  # G1 40 $/MWh 1500 MW, G2 20 1000, G3 50 1500
GEN_BUS = (1, 2, 3)  # the same in both networks
UNCONGESTED = 10_000.0
LAMBDA = ed.LAMBDA

NETWORKS = {
    "A": dict(
        label="Lecture three-bus loop", n=3,
        lines=(("1-2", 1, 2), ("1-3", 1, 3), ("2-3", 2, 3)),
        demands={1: 300.0, 2: 0.0, 3: 2000.0},
        sliders={1: (0, 600), 3: (1000, 2600)},
        switchable=("1-3",), rating_min={"2-3": 400},
        pos={1: (0.0, 0.0), 2: (5.0, 0.0), 3: (2.5, 3.6)},
        tags={1: (-2.6, 0.25), 2: (5.7, 0.25), 3: (1.4, 5.0)},  # top of each tag stack
    ),
    "B": dict(
        label="Four-bus mesh", n=4,
        lines=(("1-2", 1, 2), ("2-3", 2, 3), ("3-4", 3, 4), ("1-4", 1, 4), ("2-4", 2, 4)),
        demands={1: 0.0, 2: 0.0, 3: 500.0, 4: 1800.0},
        sliders={3: (0, 1000), 4: (1000, 2400)},
        switchable=("1-2", "2-3", "3-4", "1-4", "2-4"), rating_min={},
        pos={1: (0.0, 4.0), 2: (5.0, 4.0), 3: (5.0, 0.0), 4: (0.0, 0.0)},
        tags={1: (-0.7, 5.3), 2: (4.3, 5.3), 3: (5.7, 0.25), 4: (-2.6, 0.25)},
    ),
}


def _z(x) -> float:
    """HiGHS round-off and -0.0 off a number students read."""
    x = float(x)
    return 0.0 if abs(x) < 1e-9 else x


# --- Network mode solver ----------------------------------------------------

def islanded(net: str, out=()) -> bool:
    """True if some bus has no in-service path to bus 1."""
    spec = NETWORKS[net]
    seen, stack = {1}, [1]
    live = [(i, j) for name, i, j in spec["lines"] if name not in out]
    while stack:
        b = stack.pop()
        for i, j in live:
            for a, c in ((i, j), (j, i)):
                if a == b and c not in seen:
                    seen.add(c)
                    stack.append(c)
    return len(seen) < spec["n"]


def solve(net: str, ratings=None, out=(), demands=None) -> dict:
    """The DC OPF. ratings and demands override the defaults by line name and bus."""
    spec = NETWORKS[net]
    n = spec["n"]
    F = {name: 1500.0 for name, _, _ in spec["lines"]} | dict(ratings or {})
    Dd = spec["demands"] | dict(demands or {})
    D = [float(Dd[i]) for i in range(1, n + 1)]
    live = [line for line in spec["lines"] if line[0] not in out]
    ng, nl = len(GENS), len(live)
    N = ng + nl + n
    c = [g.offer for g in GENS] + [0.0] * (nl + n)
    A = np.zeros((n + nl, N))
    for k, bus in enumerate(GEN_BUS):
        A[bus - 1, k] = 1.0
    for m, (_, i, j) in enumerate(live):
        A[i - 1, ng + m] = -1.0
        A[j - 1, ng + m] = 1.0
        A[n + m, ng + m] = 1.0
        A[n + m, ng + nl + i - 1] = -B
        A[n + m, ng + nl + j - 1] = B
    bounds = ([(0.0, g.capacity) for g in GENS]
              + [(-F[name], F[name]) for name, _, _ in live]
              + [(0.0, 0.0)] + [(None, None)] * (n - 1))  # delta_1 = 0
    res = linprog(c, A_eq=A, b_eq=D + [0.0] * nl, bounds=bounds, method="highs")
    if not res.success:
        return dict(ok=False)
    y, lo, up, x = res.eqlin.marginals, res.lower.marginals, res.upper.marginals, res.x
    names = [name for name, _, _ in spec["lines"]]
    f = dict.fromkeys(names)
    rho, sig_up, sig_lo = dict(f), dict(f), dict(f)
    for m, (name, _, _) in enumerate(live):
        f[name] = _z(x[ng + m])
        rho[name] = _z(y[n + m])
        sig_up[name] = _z(-up[ng + m])
        sig_lo[name] = _z(lo[ng + m])
    return dict(
        ok=True, net=net, F=F, D=D, out=tuple(out),
        P=[_z(v) for v in x[:ng]], f=f, delta=[_z(v) for v in x[ng + nl:]],
        lam=[_z(v) for v in y[:n]], rho=rho, sig_up=sig_up, sig_lo=sig_lo,
        mu_up=[_z(-v) for v in up[:ng]], mu_lo=[_z(v) for v in lo[:ng]],
        cost=_z(res.fun),
    )


def _sub(name: str) -> str:
    return name.replace("-", "")


def rules(r: dict) -> dict:
    """The three stationarity rules, one row per generator, line and bus.

    Each row is (label, symbolic, substituted, lhs, rhs). A row passes when
    |lhs - rhs| <= 1e-6.
    """
    spec = NETWORKS[r["net"]]
    lam = r["lam"]
    rows = {"P": [], "f": [], "d": []}
    for k, (g, bus) in enumerate(zip(GENS, GEN_BUS)):
        rhs = g.offer + r["mu_up"][k] - r["mu_lo"][k]
        rows["P"].append((
            f"{g.name} at bus {bus}",
            rf"\lambda_{bus} = c_{k + 1} + \bar{{\mu}}_{k + 1} - \underline{{\mu}}_{k + 1}",
            rf"{_m(lam[bus - 1])} = {_m(g.offer)} + {_p(r['mu_up'][k])} - {_p(r['mu_lo'][k])}",
            lam[bus - 1], rhs))
    live = [line for line in spec["lines"] if r["f"][line[0]] is not None]
    for name, i, j in live:
        s = _sub(name)
        su, sl, rh = r["sig_up"][name], r["sig_lo"][name], r["rho"][name]
        rows["f"].append((
            f"Line {name} (from {i} to {j})",
            rf"\lambda_{j} - \lambda_{i} = \bar{{\sigma}}_{{{s}}} - \underline{{\sigma}}_{{{s}}} - \rho_{{{s}}}",
            rf"{_m(lam[j - 1])} - {_p(lam[i - 1])} = {_p(su)} - {_p(sl)} - {_p(rh)}",
            lam[j - 1] - lam[i - 1], su - sl - rh))
    for bus in range(2, spec["n"] + 1):
        sym, num, total = [], [], 0.0
        touching = sorted((line for line in live if bus in line[1:]), key=lambda l: l[1] != bus)
        for name, i, j in touching:  # lines out of the bus first, as the lectures write it
            sign = 1 if i == bus else -1  # out of the bus positive, into it negative
            s = _sub(name)
            op = "-" if sign < 0 else ("+" if sym else "")
            sym.append(rf"{op} \rho_{{{s}}} B_{{{s}}}")
            num.append(rf"{op} {_p(r['rho'][name])}({round(B)})")
            total += sign * r["rho"][name] * B
        rows["d"].append((f"Bus {bus}", " ".join(sym) + " = 0",
                          " ".join(num) + f" = {_m(total)}", total, 0.0))
    return rows


def failures(rows: dict) -> list:
    return [(rule, row) for rule, rs in rows.items() for row in rs
            if abs(row[3] - row[4]) > EPS]


def probe(net, ratings, out, demands, bus):
    """(dP per generator, dcost) for one more MW at `bus`, or None if infeasible."""
    base = solve(net, ratings, out, demands)
    more = NETWORKS[net]["demands"] | dict(demands or {})
    more[bus] = more[bus] + 1.0
    up = solve(net, ratings, out, more)
    if not (base["ok"] and up["ok"]):
        return None
    return [_z(a - b) for a, b in zip(up["P"], base["P"])], up["cost"] - base["cost"]


def settlement(r: dict) -> dict:
    spec = NETWORKS[r["net"]]
    lam = r["lam"]
    consumers = sum(d * l for d, l in zip(r["D"], lam))
    generators = sum(p * lam[b - 1] for p, b in zip(r["P"], GEN_BUS))
    live = [line for line in spec["lines"] if r["f"][line[0]] is not None]
    by_flow = sum(r["f"][name] * (lam[j - 1] - lam[i - 1]) for name, i, j in live)
    # A line binding to-from has f = -F-bar, so its term is sigma-underbar x F-bar.
    by_sigma = sum((r["sig_up"][name] + r["sig_lo"][name]) * r["F"][name] for name, _, _ in live)
    free = solve(r["net"], {name: UNCONGESTED for name, _, _ in spec["lines"]},
                 r["out"], dict(enumerate(r["D"], start=1)))
    return dict(consumers=_z(consumers), generators=_z(generators),
                rent=_z(consumers - generators), by_flow=_z(by_flow),
                by_sigma=_z(by_sigma), free_cost=free["cost"],
                congestion_cost=_z(r["cost"] - free["cost"]))


def decomposition(r: dict) -> dict:
    """a[line][bus]: change in f_l for 1 MW in at bus, out at bus 1, and the split of lambda."""
    spec = NETWORKS[r["net"]]
    n = spec["n"]
    live = [line for line in spec["lines"] if r["f"][line[0]] is not None]
    Bbus = np.zeros((n, n))
    for _, i, j in live:
        for a, b in ((i, j), (j, i)):
            Bbus[a - 1, a - 1] += B
            Bbus[a - 1, b - 1] -= B
    inv = np.linalg.inv(Bbus[1:, 1:])
    a = {}
    for name, i, j in live:
        row = [0.0]
        for bus in range(2, n + 1):
            d = np.zeros(n)
            d[1:] = inv[:, bus - 2]
            row.append(_z(B * (d[i - 1] - d[j - 1])))
        a[name] = row
    congestion = [_z(-sum(a[name][b] * (r["sig_up"][name] - r["sig_lo"][name]) for name, _, _ in live))
                  for b in range(n)]
    return dict(a=a, congestion=congestion,
                ok=all(abs(r["lam"][0] + congestion[b] - r["lam"][b]) <= EPS for b in range(n)))


# --- Losses mode solver -----------------------------------------------------

def _cost_B(R: float) -> float:
    """Merit-order cost at node B: G1 then G3."""
    p1 = min(max(R, 0.0), 1500.0)
    return 40.0 * p1 + 50.0 * (R - p1)


def _f_for(K: float, DB: float, target: float):
    """The f with D_B - f + K f^2 = target on the decreasing branch, or None."""
    q = DB - target
    disc = 1.0 - 4.0 * K * q
    if disc < 0:
        return None
    return 2.0 * q / (1.0 + math.sqrt(disc))


def _prices_at(lam, P, caps, offers):
    mu_up = [_z(lam[k] - offers[k]) if P[k] >= caps[k] - EPS else 0.0 for k in range(3)]
    mu_lo = [_z(offers[k] - lam[k]) if P[k] <= EPS else 0.0 for k in range(3)]
    return [max(v, 0.0) for v in mu_up], [max(v, 0.0) for v in mu_lo]


def losses_nlp(K: float, c2: float, DA: float, DB: float) -> dict:
    """Losses in node B's balance. K per MW, f from A to B.

    With P2 = f + D_A the cost is convex in f alone, so a bounded scalar search
    finds it, then the answer is polished against the exact candidates: the
    interval ends, the G1 kink at R = 1500 and each segment's stationary point
    c2 = p (1 - 2 K f).
    """
    R = lambda f: DB - f + K * f * f  # what G1 and G3 must supply
    g = lambda f: c2 * (f + DA) + _cost_B(R(f))
    lo = max(-DA, _f_for(K, DB, 3000.0))
    top = _f_for(K, DB, 0.0)
    hi = 1000.0 - DA if top is None else min(1000.0 - DA, top)
    if lo > hi + EPS:
        return dict(ok=False)
    cands = [lo, hi]
    kink = _f_for(K, DB, 1500.0)
    if kink is not None:
        cands.append(kink)
    if K > 0:
        cands += [(1.0 - c2 / p) / (2.0 * K) for p in (40.0, 50.0)]
    if hi > lo:
        cands.append(minimize_scalar(g, bounds=(lo, hi), method="bounded").x)
    f = min((x for x in cands if lo - EPS <= x <= hi + EPS), key=g)
    f = min(max(f, lo), hi)
    P2 = f + DA
    Rf = R(f)
    P1 = min(max(Rf, 0.0), 1500.0)
    P3 = max(Rf - P1, 0.0)
    mlf = 1.0 - 2.0 * K * f
    if EPS < P2 < 1000.0 - EPS:
        lamA, lamB = c2, c2 / mlf
    else:
        if EPS < P1 < 1500.0 - EPS:
            lamB = 40.0
        elif EPS < P3 < 1500.0 - EPS:
            lamB = 50.0
        else:  # degenerate: the next MW at B comes from the next unit up
            lamB = 50.0 if Rf >= 1500.0 - EPS else 40.0
        lamA = mlf * lamB
    return _loss_result(K, c2, DA, DB, [P1, P2, P3], f, mlf, lamA, lamB)


def losses_nemde(K: float, c2: float, DA: float, DB: float, fhat: float) -> dict:
    """Lossless dispatch with a static MLF from the study flow, offers referred to B."""
    mlf = 1.0 - 2.0 * K * fhat
    allowance = K * fhat ** 2
    res = linprog([40.0, c2 / mlf, 50.0], A_eq=[[1.0, 1.0, 1.0]], b_eq=[DA + DB + allowance],
                  bounds=[(0.0, 1500.0), (0.0, 1000.0), (0.0, 1500.0)], method="highs")
    if not res.success:
        return dict(ok=False)
    P = [_z(v) for v in res.x]
    rrp = _z(res.eqlin.marginals[0])
    out = _loss_result(K, c2, DA, DB, P, P[1] - DA, mlf, mlf * rrp, rrp)
    out.update(allowance=allowance, forecast_error=allowance - out["L"])
    return out


def _loss_result(K, c2, DA, DB, P, f, mlf, lamA, lamB) -> dict:
    P = [_z(v) for v in P]
    offers = [40.0, c2, 50.0]
    node_lam = [lamB, lamA, lamB]
    mu_up, mu_lo = _prices_at(node_lam, P, [1500.0, 1000.0, 1500.0], offers)
    L = K * f * f
    consumers = DA * lamA + DB * lamB
    generators = P[1] * lamA + (P[0] + P[2]) * lamB
    return dict(ok=True, P=P, f=_z(f), L=_z(L), MLF=mlf, lamA=_z(lamA), lamB=_z(lamB),
                mu_up=mu_up, mu_lo=mu_lo, offers=offers,
                cost=40.0 * P[0] + c2 * P[1] + 50.0 * P[2],
                consumers=_z(consumers), generators=_z(generators),
                residue=_z(consumers - generators), residue_identity=_z(lamB * L),
                discount=_z(lamB * 2.0 * K * f * P[1]))


# --- Formatting -------------------------------------------------------------

def _n(x: float) -> str:
    """Two decimals, and no trailing .00 on an integer."""
    s = f"{round(float(x), 2) + 0.0:,.2f}"
    return s[:-3] if s.endswith(".00") else s


def _m(x: float) -> str:
    """_n for maths: KaTeX spaces a bare comma."""
    return _n(x).replace(",", "{,}")


def _p(x: float) -> str:
    """A negative number wrapped in brackets, for substituting into an expression."""
    return f"({_m(x)})" if round(x, 2) < 0 else _m(x)


def _pipe_table(head: list[str], rows: list[list[str]]) -> str:
    """A markdown table, so its cells reach KaTeX."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _gen_status(P, cap, price_bus: str) -> str:
    if P >= cap - EPS:
        return "at capacity"
    if P <= EPS:
        return "off"
    return rf"marginal: sets $\lambda_{{{price_bus}}}$ at its bus"


def _dispatch_table(P, offers, mu_up, mu_lo, buses) -> str:
    head = ["Unit", "Bus", r"Offer $c_k$ (\$/MWh)", r"Output $P_k$ (MW)", "Status",
            r"$\bar{\mu}_k$", r"$\underline{\mu}_k$"]
    rows = [[g.name, str(bus), _n(offers[k]), _n(P[k]),
             _gen_status(P[k], g.capacity, bus), _n(mu_up[k]), _n(mu_lo[k])]
            for k, (g, bus) in enumerate(zip(GENS, buses))]
    return _pipe_table(head, rows)


def _line_table(r) -> str:
    head = ["Line", "From to", r"$f_\ell$ (MW)", r"$\bar{F}_\ell$ (MW)", "Status",
            r"$\bar{\sigma}_\ell$", r"$\underline{\sigma}_\ell$", r"$\rho_\ell$"]
    rows = []
    for name, i, j in NETWORKS[r["net"]]["lines"]:
        f, F = r["f"][name], r["F"][name]
        if f is None:
            rows.append([name, f"{i} to {j}", "", _n(F), "out of service", "", "", ""])
            continue
        status = ("binding, from-to" if f >= F - EPS else
                  "binding, to-from" if f <= -F + EPS else "below rating")
        rows.append([name, f"{i} to {j}", _n(f), _n(F), status, _n(r["sig_up"][name]),
                     _n(r["sig_lo"][name]), _n(r["rho"][name])])
    return _pipe_table(head, rows)


# --- Charts -----------------------------------------------------------------

def _layout(fig, title, height=520):
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=ed.NAVY)),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=14, color=ed.NAVY), orientation="h", y=-0.2),
        height=height, margin=dict(t=60, b=40, l=40, r=40), showlegend=False,
    )


def _bare_axes(fig, xr, yr):
    fig.update_xaxes(visible=False, range=xr)
    fig.update_yaxes(visible=False, range=yr, scaleanchor="x", scaleratio=1)


def _draw_line(fig, p0, p1, f, label, colour, width, dash="solid", offset=0.6):
    (x0, y0), (x1, y1) = p0, p1
    fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="skip",
                             line=dict(color=colour, width=width, dash=dash)))
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


def _network_diagram(r) -> go.Figure:
    spec = NETWORKS[r["net"]]
    pos = spec["pos"]
    fig = go.Figure()
    for name, i, j in spec["lines"]:
        f, F = r["f"][name], r["F"][name]
        if f is None:
            _draw_line(fig, pos[i], pos[j], None, f"{name} out", ed.MUTED, 3, "dash")
        elif abs(f) >= F - EPS:
            _draw_line(fig, pos[i], pos[j], f, f"<b>{abs(f):,.0f} / {F:,.0f} MW</b>", ed.PURPLE, 8)
        else:
            _draw_line(fig, pos[i], pos[j], f, f"{abs(f):,.0f} / {F:,.0f} MW", ed.NAVY, 4)
    for bus, (x, y) in pos.items():
        tags = []
        if bus in GEN_BUS:
            k = GEN_BUS.index(bus)
            tags.append((f"{GENS[k].name} {_n(r['P'][k])} MW", "square", ed.LAVENDER))
        if bus in spec["sliders"]:
            tags.append((f"D<sub>{bus}</sub> {_n(r['D'][bus - 1])} MW", "triangle-down",
                         ed.LIMESTONE))
        tx, ty = spec["tags"][bus]
        for t, (text, symbol, colour) in enumerate(tags):
            _draw_tag(fig, tx, ty - 0.5 * t, text, symbol, colour)
        _draw_bus(fig, x, y, f"Bus {bus}", r["lam"][bus - 1])
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    _bare_axes(fig, [min(xs) - 2.8, max(xs) + 3.0], [min(ys) - 1.4, max(ys) + 1.8])
    _layout(fig, "Nodal prices and flows", height=560)
    return fig


def _losses_diagram(r, DA, DB) -> go.Figure:
    fig = go.Figure()
    a, b = (0.0, 0.0), (6.0, 0.0)
    _draw_line(fig, a, b, r["f"],
               f"f = {_n(r['f'])} MW, L = {_n(r['L'])} MW, MLF<sub>A</sub> = {r['MLF']:.4f}",
               ed.NAVY, 4, offset=0.9)
    _draw_tag(fig, -1.2, 1.3, f"G2 {_n(r['P'][1])} MW", "square", ed.LAVENDER)
    _draw_tag(fig, -1.2, -1.6, f"D<sub>A</sub> {_n(DA)} MW", "triangle-down", ed.LIMESTONE)
    _draw_tag(fig, 6.2, 1.6, f"G1 {_n(r['P'][0])} MW", "square", ed.LAVENDER)
    _draw_tag(fig, 6.2, 1.0, f"G3 {_n(r['P'][2])} MW", "square", ed.LAVENDER)
    _draw_tag(fig, 6.2, -1.6, f"D<sub>B</sub> {_n(DB)} MW", "triangle-down", ed.LIMESTONE)
    _draw_bus(fig, *a, "Node A", r["lamA"])
    _draw_bus(fig, *b, "Node B", r["lamB"])
    _bare_axes(fig, [-2.0, 9.5], [-2.3, 2.3])
    _layout(fig, "Two nodes, one lossy line", height=420)
    return fig


def _chord_chart(K, f) -> go.Figure:
    s = -1.0 if f < 0 else 1.0
    xs = np.linspace(0.0, 1500.0, 301) * s
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=K * xs ** 2, mode="lines",
                             line=dict(color=ed.NAVY, width=4), name="L(f) = K f²"))
    L = K * f * f
    fig.add_trace(go.Scatter(x=[0.0, s * 1500.0], y=[0.0, K * f * s * 1500.0], mode="lines",
                             line=dict(color=ed.MUTED, width=3, dash="dash"), name="chord"))
    fig.add_trace(go.Scatter(x=xs, y=L + 2.0 * K * f * (xs - f), mode="lines",
                             line=dict(color=ed.PURPLE, width=3), name="tangent"))
    fig.add_trace(go.Scatter(x=[f], y=[L], mode="markers",
                             marker=dict(size=16, color=ed.PURPLE, line=dict(color=ed.NAVY, width=2))))
    top = max(K * 1500.0 ** 2, 1.0)
    fig.add_annotation(x=s * 1100.0, y=K * abs(f) * 1100.0, text=f"average loss K f = {100 * K * abs(f):.2f} %",
                       showarrow=False, yshift=-22, font=dict(size=17, color=ed.MUTED), bgcolor="#FFFFFF")
    fig.add_annotation(x=f, y=L, text=f"marginal loss 2K f = {200 * K * abs(f):.2f} %",
                       showarrow=True, ax=-s * 90, ay=-50, font=dict(size=17, color=ed.PURPLE),
                       bgcolor="#FFFFFF", arrowcolor=ed.PURPLE)
    fig.update_layout(
        xaxis=dict(title=dict(text="flow f (MW)", font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER),
        yaxis=dict(title=dict(text="loss L (MW)", font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER, range=[0, top * 1.08]))
    _layout(fig, "Chord and tangent: average and marginal loss", height=440)
    return fig


# --- The page ---------------------------------------------------------------

def _k(net, what, name) -> str:
    return f"np_{net}_{what}_{name}"


def _preset(net, ratings=None, out=()) -> dict:
    spec = NETWORKS[net]
    v = {}
    for name, _, _ in spec["lines"]:
        v[_k(net, "F", name)] = int((ratings or {}).get(name, 1500))
        v[_k(net, "on", name)] = name not in out
    for bus in spec["sliders"]:
        v[_k(net, "D", bus)] = int(spec["demands"][bus])
    return v


PRESETS = {
    "A": {
        "Case A: nothing binds": _preset("A"),
        "Case B: line 2-3 at 800": _preset("A", {"2-3": 800}),
        "Line 2-3 at 400: price above every offer": _preset("A", {"2-3": 400}),
        "Radial: line 1-3 out, 2-3 at 800": _preset("A", {"2-3": 800}, ("1-3",)),
    },
    "B": {
        "Nothing binds": _preset("B"),
        "Line 1-4 at 700": _preset("B", {"1-4": 700}),
        "Line 2-3 at 500": _preset("B", {"2-3": 500}),
        "Chord 2-4 at 600": _preset("B", {"2-4": 600}),
        "Radial star: 1-2 and 2-3 out, 1-4 at 700": _preset("B", {"1-4": 700}, ("1-2", "2-3")),
    },
}

NLP, NEMDE = "Losses in the balance (NLP)", "NEMDE style: lossless dispatch with a static MLF"
LOSS_BASE = {"np_K": 2.0, "np_c2": 20.0, "np_DA": 0, "np_DB": 2300, "np_disp": NLP, "np_fhat": 1000}
LOSS_PRESETS = {
    "Lossless (K = 0)": {**LOSS_BASE, "np_K": 0.0},
    "Part V (K = 2 × 10⁻⁵)": LOSS_BASE,
    "Close call: G2 offers 38.5": {**LOSS_BASE, "np_c2": 38.5},
    "Reverse flow: D_A 1500, D_B 800": {**LOSS_BASE, "np_DA": 1500, "np_DB": 800},
    "Close call, NEMDE style": {**LOSS_BASE, "np_c2": 38.5, "np_disp": NEMDE},
}

DEFAULTS = {"np_mode": "Network", "np_net": "A", "np_probe_bus": 2,
            **PRESETS["A"]["Case A: nothing binds"], **PRESETS["B"]["Nothing binds"], **LOSS_BASE}


def _presets_row(presets, prefix) -> None:
    for column, (label, values) in zip(st.columns(len(presets)), presets.items()):
        column.button(label, key=f"{prefix}{label}", width="stretch",
                      on_click=lambda v=values: st.session_state.update(v))


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "Where the price comes from: flows, congestion and losses",
        "One more megawatt at a bus costs its nodal price. Move a rating or add "
        "resistance and watch who pays what.",
    )
    st.markdown(
        f"""<style>
[data-testid="stMarkdownContainer"] table {{ width: 100%; border-collapse: collapse; }}
[data-testid="stMarkdownContainer"] th, [data-testid="stMarkdownContainer"] td {{
  text-align: center; padding: .45rem .5rem; border-bottom: 1px solid {ed.SILVER};
}}
[data-testid="stMarkdownContainer"] th {{ border-bottom: 2px solid {ed.SILVER}; }}
</style>""", unsafe_allow_html=True)

    mode = st.radio("Mode", ["Network", "Losses"], horizontal=True, key="np_mode")
    if mode == "Network":
        _network_page()
    else:
        _losses_page()


def _network_page() -> None:
    net = st.radio("Network", ["A", "B"], horizontal=True, key="np_net",
                   format_func=lambda k: NETWORKS[k]["label"])
    spec = NETWORKS[net]
    st.subheader("Presets")
    _presets_row(PRESETS[net], f"np_{net}_preset_")

    st.subheader(r"Lines: rating $\bar{F}_\ell$ (MW)")
    st.caption(rf"Every line is {V:.0f} kV with $X_\ell = {X}$ Ω, so "
               rf"$B_\ell = V^2 / X_\ell = {B:,.0f}$ MW/rad.")
    for column, (name, i, j) in zip(st.columns(len(spec["lines"])), spec["lines"]):
        s = _sub(name)
        column.slider(rf"$\bar{{F}}_{{{s}}}$, line {name}", spec["rating_min"].get(name, 300),
                      1500, step=50, key=_k(net, "F", name))
        column.checkbox("in service", key=_k(net, "on", name),
                        disabled=name not in spec["switchable"])

    st.subheader(r"Demand $D_i$ (MW)")
    for column, (bus, (lo, hi)) in zip(st.columns(len(spec["sliders"])), spec["sliders"].items()):
        column.slider(rf"$D_{bus}$", lo, hi, step=50, key=_k(net, "D", bus))

    ss = st.session_state
    ratings = {name: float(ss[_k(net, "F", name)]) for name, _, _ in spec["lines"]}
    out = tuple(name for name, _, _ in spec["lines"] if not ss[_k(net, "on", name)])
    demands = {bus: float(ss[_k(net, "D", bus)]) for bus in spec["sliders"]}

    if islanded(net, out):
        ed.note("**Islanded.** Every bus must stay connected to bus 1.")
        return
    r = solve(net, ratings, out, demands)
    if not r["ok"]:
        ed.note("**No dispatch.** Demand cannot be served within these ratings and capacities.")
        return

    st.plotly_chart(_network_diagram(r), width="stretch")
    st.caption("Arrows point the way the power actually flows. A purple line is at "
               "its rating; a dashed line is out of service.")

    st.subheader("Dispatch")
    st.markdown(_dispatch_table(r["P"], [g.offer for g in GENS], r["mu_up"], r["mu_lo"],
                                GEN_BUS), unsafe_allow_html=True)
    st.markdown(rf"Dispatch cost $\sum_k c_k P_k = {_m(r['cost'])}$ \$/h.")
    st.subheader("Lines")
    st.markdown(_line_table(r), unsafe_allow_html=True)

    _rules_panel(r)
    _probe_panel(net, ratings, out, demands, r)
    _settlement_panel(r)
    _decomposition_panel(r)


def _rules_panel(r) -> None:
    st.subheader("Check every price")
    rows = rules(r)
    bad = failures(rows)
    if bad:
        rule, row = bad[0]
        ed.note(f"**Solver multipliers failed the stationarity check.** Rule "
                f"{'δ' if rule == 'd' else rule}, {row[0]}: ${row[2]}$.")
    titles = {"P": "Rule P: a marginal unit prices its own bus",
              "f": "Rule f: the price across a line",
              "d": "Rule δ: a current law on ρB"}
    for rule, title in titles.items():
        with st.expander(title, expanded=True):
            st.markdown("\n".join(
                rf"- {label}: ${sym} \quad\to\quad {num}$ "
                + ("✓" if abs(lhs - rhs) <= EPS else "✗")
                for label, sym, num, lhs, rhs in rows[rule]))


def _probe_panel(net, ratings, out, demands, r) -> None:
    st.subheader("Probe")
    n = NETWORKS[net]["n"]
    c1, c2 = st.columns([3, 1])
    bus = c1.selectbox("Serve 1 MW more at bus", list(range(1, n + 1)), key="np_probe_bus")
    c2.markdown("&nbsp;")
    if not c2.button("Probe", key="np_probe_go", width="stretch"):
        return
    result = probe(net, ratings, out, demands, bus)
    if result is None:
        ed.note(f"**No dispatch.** One more MW at bus {bus} cannot be served.")
        return
    dP, dcost = result
    st.markdown(_pipe_table(["Unit", r"$\Delta P_k$ (MW)"],
                            [[g.name, f"{d:+,.2f}"] for g, d in zip(GENS, dP)]))
    lam = r["lam"][bus - 1]
    st.markdown(rf"Cost rises by **{_n(dcost)} \$/h**, which equals $\lambda_{bus} = {_m(lam)}$ "
                + ("✓" if abs(dcost - lam) <= EPS else "✗"))
    if abs(dcost - lam) > EPS:
        ed.note("This demand sits on a kink: the multiplier is the price on one "
                "side of it and the extra megawatt lands on the other.")


def _settlement_panel(r) -> None:
    st.subheader(r"Settlement (\$/h)")
    s = settlement(r)
    spec = NETWORKS[r["net"]]
    binding = [(name, r["sig_up"][name] + r["sig_lo"][name], r["F"][name])
               for name, _, _ in spec["lines"]
               if r["f"][name] is not None and r["sig_up"][name] + r["sig_lo"][name] > EPS]
    parts = " + ".join(rf"{_m(F)} \times {_m(sig)}" for _, sig, F in binding) or "0"
    rows = [
        [r"Consumers pay $\sum_i D_i \lambda_i$", _n(s["consumers"])],
        [r"Generators receive $\sum_k P_k \lambda_{i(k)}$", _n(s["generators"])],
        ["Congestion rent, the difference", _n(s["rent"])],
        [r"Rent as $\sum_\ell f_\ell (\lambda_{to} - \lambda_{from})$", _n(s["by_flow"])],
        [rf"Rent as $\sum_{{\ell\ \text{{binding}}}} (\bar{{\sigma}}_\ell + \underline{{\sigma}}_\ell) "
         rf"\bar{{F}}_\ell = {parts}$", _n(s["by_sigma"])],
        [rf"Cost of congestion: ${_m(r['cost'])} - {_m(s['free_cost'])}$, the second with "
         r"every rating at 10 000 MW", _n(s["congestion_cost"])],
    ]
    st.markdown(_pipe_table(["", r"\$/h"], rows), unsafe_allow_html=True)
    ed.note("Congestion rent is what the price differences collect from the flows. "
            "Cost of congestion is how much more the dispatch costs because of the "
            "ratings. They are different numbers.")


def _decomposition_panel(r) -> None:
    d = decomposition(r)
    n = NETWORKS[r["net"]]["n"]
    congested = [name for name in d["a"]
                 if abs(r["sig_up"][name] - r["sig_lo"][name]) > EPS]
    with st.expander("Energy plus congestion", expanded=False):
        st.markdown(r"With bus 1 as the reference, "
                    r"$\lambda_i = \lambda_1 - \sum_\ell a_{\ell,i} (\bar{\sigma}_\ell - \underline{\sigma}_\ell)$, "
                    r"where $a_{\ell,i}$ is the change in $f_\ell$ when 1 MW is injected at bus $i$ "
                    "and withdrawn at bus 1.")
        head = ["Bus"] + [rf"$a_{{{_sub(name)},i}}$" for name in congested] + [
            r"$\lambda_1$", "congestion component", r"$\lambda_i$"]
        rows = [[str(b + 1)] + [_n(d["a"][name][b]) for name in congested]
                + [_n(r["lam"][0]), _n(d["congestion"][b]), _n(r["lam"][b])] for b in range(n)]
        st.markdown(_pipe_table(head, rows), unsafe_allow_html=True)
        if not d["ok"]:
            ed.note("Solver multipliers failed the stationarity check: the energy and "
                    "congestion components do not add up to the nodal price.")


def _losses_page() -> None:
    st.subheader("Presets")
    _presets_row(LOSS_PRESETS, "np_loss_preset_")
    c1, c2, c3, c4 = st.columns(4)
    c1.slider(r"$K$ ($\times 10^{-5}$ per MW)", 0.0, 10.0, step=0.1, key="np_K")
    K = float(st.session_state["np_K"]) * 1e-5
    c1.markdown(rf"$R = K V^2 = {K * V ** 2:.3f}$ Ω")
    c2.number_input(r"$c_2$, G2's offer (\$/MWh)", min_value=0.0, max_value=60.0,
                    step=0.5, key="np_c2")
    c3.slider(r"$D_A$ (MW)", 0, 1500, step=50, key="np_DA")
    c4.slider(r"$D_B$ (MW)", 0, 3000, step=50, key="np_DB")
    disp = st.radio("Dispatch", [NLP, NEMDE], key="np_disp")
    ss = st.session_state
    c2v, DA, DB = float(ss["np_c2"]), float(ss["np_DA"]), float(ss["np_DB"])
    if disp == NEMDE:
        st.slider(r"Study flow $\hat{f}$ (MW)", 0, 1500, step=50, key="np_fhat")
        fhat = float(ss["np_fhat"])
        st.caption(rf"Static $\text{{MLF}}_A = 1 - 2K\hat{{f}} = {1 - 2 * K * fhat:.4f}$ and a loss "
                   rf"allowance $K\hat{{f}}^2 = {K * fhat ** 2:,.2f}$ MW added to $D_B$.")
        r = losses_nemde(K, c2v, DA, DB, fhat)
    else:
        r = losses_nlp(K, c2v, DA, DB)
    if not r["ok"]:
        ed.note("**No dispatch.** Demand cannot be served within these ratings and capacities.")
        return

    st.plotly_chart(_losses_diagram(r, DA, DB), width="stretch")
    st.plotly_chart(_chord_chart(K, r["f"]), width="stretch")
    cols = st.columns(5)
    for column, (label, value) in zip(cols, [
            (r"$f$ (MW)", _n(r["f"])), (r"$L = K f^2$ (MW)", _n(r["L"])),
            (r"$\text{MLF}_A$", f"{r['MLF']:.4f}"),
            (r"$\lambda_A$ (\$/MWh)", f"{r['lamA']:,.2f}"),
            (r"$\lambda_B$ (\$/MWh)", f"{r['lamB']:,.2f}")]):
        with column:
            ed.headline(label, value)
    st.markdown(r"$\lambda_A = (1 - 2Kf)\,\lambda_B = \text{MLF}_A \, \lambda_B$, whichever way the line flows.")
    if disp == NEMDE:
        st.markdown(rf"Offers are referred to node B: G2 is dispatched at "
                    rf"$c_2 / \text{{MLF}}_A = {_m(c2v / r['MLF'])}$. RRP $= \lambda_B = {_m(r['lamB'])}$ "
                    rf"and G2 is paid $\text{{MLF}}_A \times \text{{RRP}} = {_m(r['lamA'])}$. Actual "
                    rf"losses $K f^2 = {_m(r['L'])}$ MW, so the loss forecast error "
                    rf"$K\hat{{f}}^2 - K f^2 = {_m(r['forecast_error'])}$ MW.")

    st.subheader("Dispatch")
    st.markdown(_dispatch_table(r["P"], r["offers"], r["mu_up"], r["mu_lo"], ("B", "A", "B")),
                unsafe_allow_html=True)

    st.subheader(r"Settlement (\$/h)")
    rows = [[r"Consumers pay $D_A \lambda_A + D_B \lambda_B$", _n(r["consumers"])],
            [r"Generators receive $P_2 \lambda_A + (P_1 + P_3) \lambda_B$", _n(r["generators"])],
            ["Loss residue, the difference", _n(r["residue"])]]
    if disp == NLP:
        rows.append([r"Residue as $\lambda_B K f^2$", _n(r["residue_identity"])])
    st.markdown(_pipe_table(["", r"\$/h"], rows), unsafe_allow_html=True)
    if disp == NEMDE:
        st.caption(r"With a static MLF the residue is no longer $\lambda_B K f^2$: the loss "
                   "allowance was a forecast, and the actual flow differs from the study flow.")
    elif r["f"] > EPS and DA == 0:
        st.markdown("**Collected twice.**")
        st.markdown(_pipe_table(["", r"\$/h"], [
            [r"G2's discount $\lambda_B \cdot 2Kf \cdot P_2$", _n(r["discount"])],
            [r"Cost of the physical losses $\lambda_B K f^2$", _n(r["residue_identity"])],
            ["Residue, the difference", _n(r["discount"] - r["residue_identity"])]]),
            unsafe_allow_html=True)
        st.caption(r"The marginal loss factor charges G2 for $2Kf$ per MW, twice the "
                   r"average loss $Kf$. The extra half is the residue.")
