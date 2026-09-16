"""A battery's offer is an opportunity cost (Topic 6).

A battery has no fuel cost, yet it does not offer at zero. In every interval
the optimiser writes a price for the energy inside the tank, the multiplier on
the state-of-energy row, and that price corrected for losses is the battery's
real offer and bid. The page shows that number in every interval, what one
more megawatt-hour in the tank would have done, how a large battery moves the
market price, and the complementarity failure a plain LP allows.

Sign convention, kept exactly as the lectures write it: the SOE row is
E_t = E_{t-1} + eta_ch Pch_t Delta T - Pdis_t Delta T / eta_dis with multiplier
theta_t, and the value of stored energy is v_t = -theta_t. In GAMS that is
v(t) = -soe.m(t). Scipy's eqlin.marginals is d(objective)/d(rhs) of a
minimisation, which is GAMS .m, so soe.m comes straight off the SOE rows.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from experiments._kit import ed

T = 12
DT = ed.DT
EPS = 1e-6

LAM_KEYS = tuple(f"boc_lam{t + 1}" for t in range(T))
DEMAND_KEYS = tuple(f"boc_d{t + 1}" for t in range(T))
BAT_KEYS = ("boc_P", "boc_E", "boc_E0", "boc_eta_c", "boc_eta_d", "boc_b", "boc_c")

PART_V_PRICES = (40,) * 5 + (50,) * 7
PART_V_DEMANDS = (2200, 2250, 2300, 2350, 2450, 2650, 2700, 2750, 2700, 2650, 2600, 2550)

DEFAULTS = {
    "boc_mode": "Price path",
    "boc_P": 100, "boc_E": 30, "boc_E0": 0.0,
    "boc_eta_c": 0.90, "boc_eta_d": 0.90, "boc_b": 42.0, "boc_c": 48.0,
    "boc_end_on": False, "boc_end": 0.0, "boc_binary": False,
    "boc_bat_off": False, "boc_probe_t": 7, "boc_probe_kind": "inject",
    **dict(zip(LAM_KEYS, PART_V_PRICES)),
    **dict(zip(DEMAND_KEYS, PART_V_DEMANDS)),
}

BATTERY_DEFAULTS = {k: DEFAULTS[k] for k in BAT_KEYS}

# A preset is just widget values, applied in the button callback before the
# widgets are rebuilt on the rerun, as the Topic 5 experiments do.
PRICE_PRESETS = {
    "Part V": {**BATTERY_DEFAULTS, **dict(zip(LAM_KEYS, PART_V_PRICES))},
    "Two peaks": {**BATTERY_DEFAULTS,
                  **dict(zip(LAM_KEYS, (40,) * 5 + (50, 50, 55, 55, 55, 55, 50)))},
    "Thin spread": {**BATTERY_DEFAULTS, **dict(zip(LAM_KEYS, (40,) * 5 + (48,) * 7))},
    # Only E0 is overridden. With the offer at zero as well, a 50 $/MWh
    # interval makes a round trip look profitable in declared terms and the
    # LP charges and discharges in every interval, which buries the lesson.
    "Negative price": {**BATTERY_DEFAULTS, "boc_E0": 30.0,
                       **dict(zip(LAM_KEYS, (-50,) + (50,) * 11))},
}
MARKET_PRESETS = {
    "Price taker": {"boc_P": 100, "boc_E": 30},
    "Price maker": {"boc_P": 300, "boc_E": 90},
}

LAMBDA = ed.LAMBDA
SUB_T = "ₜ"


# --- Solvers --------------------------------------------------------------

def _solve(c, A_eq, b_eq, lb, ub, A_ub=None, b_ub=None, integrality=None):
    """One LP or MILP. Returns (result, x, eq_marginals or None)."""
    if integrality is not None:
        cons = [LinearConstraint(np.array(A_eq), b_eq, b_eq)]
        if A_ub:
            cons.append(LinearConstraint(np.array(A_ub), -np.inf, b_ub))
        res = milp(c, constraints=cons, integrality=integrality, bounds=Bounds(lb, ub))
        return res, res.x, None
    res = linprog(c, A_ub=np.array(A_ub) if A_ub else None, b_ub=b_ub or None,
                  A_eq=np.array(A_eq), b_eq=b_eq, bounds=list(zip(lb, ub)),
                  method="highs")
    return res, res.x, (res.eqlin.marginals if res.success else None)


def _soe_rows(T, nv, off, bat, inject):
    """SOE rows E_t - E_{t-1} - eta_c Pch DT + Pdis DT/eta_d = rhs.

    `off` is the column offset of (Pch, Pdis, E) inside each interval's block.
    """
    N = T * nv
    A, rhs = [], []
    for t in range(T):
        r = np.zeros(N)
        r[t * nv + off + 2] = 1
        if t > 0:
            r[(t - 1) * nv + off + 2] = -1
        r[t * nv + off] = -bat["eta_c"] * DT
        r[t * nv + off + 1] = DT / bat["eta_d"]
        A.append(r)
        b = bat["E0"] if t == 0 else 0.0
        if inject and inject[0] == t:
            b += inject[1]
        rhs.append(b)
    return A, rhs


def _one_tap_rows(T, nv, off, bat):
    """Pch <= P u and Pdis <= P (1 - u), u the binary at column off + 3."""
    N = T * nv
    A, b = [], []
    for t in range(T):
        r = np.zeros(N); r[t * nv + off] = 1; r[t * nv + off + 3] = -bat["P"]
        A.append(r); b.append(0.0)
        r = np.zeros(N); r[t * nv + off + 1] = 1; r[t * nv + off + 3] = bat["P"]
        A.append(r); b.append(bat["P"])
    return A, b


def _battery_bounds(T, nv, off, bat, lb, ub, binary, e_end, force_dis):
    for t in range(T):
        ub[t * nv + off] = bat["P"]
        ub[t * nv + off + 1] = bat["P"]
        ub[t * nv + off + 2] = bat["E"]
        if binary:
            ub[t * nv + off + 3] = 1
        if e_end is not None and t == T - 1:
            lb[t * nv + off + 2] = e_end
    if force_dis:
        t, mw = force_dis
        lb[t * nv + off + 1] = ub[t * nv + off + 1] = mw


def battery_block(prices, bat, binary=False, e_end=None, inject=None, force_dis=None):
    """The battery priced at lambda: minimise minus the declared surplus.

    bat = dict(P, E, E0, eta_c, eta_d, b, c). inject=(t, MWh) adds MWh to the
    SOE right-hand side at t; force_dis=(t, MW) fixes Pdis_t. v is None when
    the one-tap binary is on, because a MILP has no multipliers.
    """
    T = len(prices)
    nv = 4 if binary else 3
    N = T * nv
    c = np.zeros(N)
    for t in range(T):
        c[t * nv] = (prices[t] - bat["b"]) * DT
        c[t * nv + 1] = (bat["c"] - prices[t]) * DT
    A, rhs = _soe_rows(T, nv, 0, bat, inject)
    lb = np.zeros(N); ub = np.full(N, np.inf)
    _battery_bounds(T, nv, 0, bat, lb, ub, binary, e_end, force_dis)
    A_ub, b_ub, integ = None, None, None
    if binary:
        A_ub, b_ub = _one_tap_rows(T, nv, 0, bat)
        integ = np.zeros(N); integ[3::4] = 1
    res, x, marg = _solve(c, A, rhs, lb, ub, A_ub, b_ub, integ)
    if not res.success:
        return dict(ok=False)
    Pch, Pdis, E = x[0::nv], x[1::nv], x[2::nv]
    return _battery_result(True, prices, Pch, Pdis, E,
                           None if marg is None else -marg, -res.fun)


def _battery_result(ok, prices, Pch, Pdis, E, v, surplus):
    # HiGHS returns -0.0 and 1e-15 on inactive taps; students read the table.
    Pch, Pdis, E = (np.where(np.abs(a) < EPS, 0.0, a) for a in (Pch, Pdis, E))
    return dict(
        ok=ok, Pch=Pch, Pdis=Pdis, E=E, v=v, surplus=float(surplus),
        bought=float(Pch.sum() * DT), sold=float(Pdis.sum() * DT),
        cash=float(sum(prices[t] * (Pdis[t] - Pch[t]) * DT for t in range(len(prices)))),
    )


def market(demands, bat, binary=False, e_end=None):
    """The operator's problem with the battery inside it.

    Variables per interval are [P_1, P_2, P_3, Pch, Pdis, E] (plus u when
    binary). lambda_t is the balance-row multiplier divided by Delta T because
    the row is in MW and the objective in dollars; theta_t is the SOE-row
    multiplier as it stands, and v_t = -theta_t.
    """
    T = len(demands)
    gens = ed.GENERATORS
    n = len(gens)
    nv = n + (4 if binary else 3)
    N = T * nv
    c = np.zeros(N)
    A_bal = []
    for t in range(T):
        for k, gen in enumerate(gens):
            c[t * nv + k] = gen.offer * DT
        c[t * nv + n] = -bat["b"] * DT
        c[t * nv + n + 1] = bat["c"] * DT
        r = np.zeros(N)
        r[t * nv:t * nv + n] = 1
        r[t * nv + n] = -1
        r[t * nv + n + 1] = 1
        A_bal.append(r)
    A_soe, rhs_soe = _soe_rows(T, nv, n, bat, None)
    lb = np.zeros(N); ub = np.full(N, np.inf)
    for t in range(T):
        for k, gen in enumerate(gens):
            ub[t * nv + k] = gen.capacity
    _battery_bounds(T, nv, n, bat, lb, ub, binary, e_end, None)
    A_ub, b_ub, integ = None, None, None
    if binary:
        A_ub, b_ub = _one_tap_rows(T, nv, n, bat)
        integ = np.zeros(N); integ[n + 3::nv] = 1
    res, x, marg = _solve(c, A_bal + A_soe, list(demands) + rhs_soe,
                          lb, ub, A_ub, b_ub, integ)
    if not res.success:
        return dict(ok=False)
    X = x.reshape(T, nv)
    P = X[:, :n]
    Pch, Pdis, E = X[:, n], X[:, n + 1], X[:, n + 2]
    if marg is None:
        # A MILP has no multipliers, so price it the way an operator would:
        # fix the integers and re-solve the LP for lambda. v stays unknown.
        lam = _fixed_lp_prices(demands, bat, Pch, Pdis)
        v = None
    else:
        lam = marg[:T] / DT
        v = -marg[T:]
    declared = -sum((lam[t] - bat["b"]) * Pch[t] * DT
                    + (bat["c"] - lam[t]) * Pdis[t] * DT for t in range(T))
    out = _battery_result(True, lam, Pch, Pdis, E, v, declared)
    out.update(
        lam=lam, P=P,
        gen_cost=float(sum(gen.offer * P[t, k] * DT for t in range(T)
                           for k, gen in enumerate(gens))),
        consumers=float(sum(lam[t] * demands[t] * DT for t in range(T))),
        rents=[float(sum((lam[t] - gen.offer) * P[t, k] * DT for t in range(T)))
               for k, gen in enumerate(gens)],
    )
    return out


def _fixed_lp_prices(demands, bat, Pch, Pdis):
    """lambda with the battery's MILP schedule held fixed: net demand pricing."""
    net = [demands[t] - Pdis[t] + Pch[t] for t in range(len(demands))]
    return np.array(ed.solve(net).lam)


def effective(v, bat):
    """(effective offer, effective bid) per interval, or (None, None) for a MILP."""
    if v is None:
        return None, None
    v = np.asarray(v)
    return bat["c"] + v / bat["eta_d"], bat["b"] + bat["eta_c"] * v


def round_trip(prices, bat):
    """(lambda_high / lambda_low, 1 / (eta_c eta_d), passes). Ratio None if lambda_low <= 0."""
    lo, hi = min(prices), max(prices)
    threshold = 1.0 / (bat["eta_c"] * bat["eta_d"])
    if lo <= 0:
        return None, threshold, True
    return hi / lo, threshold, hi / lo > threshold


def both_taps(r):
    """Intervals (0-based) where the solution charges and discharges at once."""
    return [t for t in range(len(r["Pch"]))
            if r["Pch"][t] > EPS and r["Pdis"][t] > EPS]


# --- Page furniture -------------------------------------------------------

def _num(x: float) -> str:
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}"


def _decision(t, lam, r, bat, offer, bid):
    """The short phrase in the last column of the table."""
    Pch, Pdis = r["Pch"][t], r["Pdis"][t]
    E_prev = bat["E0"] if t == 0 else r["E"][t - 1]
    if Pch > EPS and Pdis > EPS:
        return "both taps open"
    if Pdis >= bat["P"] - EPS:
        return "discharge at limit"
    if Pch >= bat["P"] - EPS:
        return "charge at limit"
    if offer is None:
        return "discharging" if Pdis > EPS else "charging" if Pch > EPS else "holding"
    if Pdis > EPS:
        return f"discharging: {_num(lam)} ≥ {offer:.2f}"
    if Pch > EPS:
        return f"charging: {_num(lam)} ≤ {bid:.2f}"
    if E_prev <= EPS and lam >= offer - EPS:
        return "holding: tank empty"
    if E_prev >= bat["E"] - EPS and lam <= bid + EPS:
        return "holding: tank full"
    if abs(lam - bid) < 1e-4:
        return f"indifferent: {_num(lam)} = {bid:.2f}"
    if abs(lam - offer) < 1e-4:
        return f"indifferent: {_num(lam)} = {offer:.2f}"
    if lam < bid:
        return f"holding: {_num(lam)} < {bid:.2f} but cannot charge"
    if lam > offer:
        return f"holding: {_num(lam)} > {offer:.2f} but cannot discharge"
    return f"holding: {bid:.2f} < {_num(lam)} < {offer:.2f}"


def _table(lam, r, bat) -> str:
    offer, bid = effective(r["v"], bat)
    grey = f'style="color:{ed.MUTED}"'
    head = "".join(f"<th>{h}</th>" for h in (
        "t", f"{LAMBDA}{SUB_T} ($/MWh)", f"P{SUB_T}ᶜʰ (MW)",
        f"P{SUB_T}ᵈⁱˢ (MW)", f"E{SUB_T} (MWh)", "soe.m", f"v{SUB_T}",
        "effective bid", "effective offer", "decision"))
    rows = ""
    for t in range(len(lam)):
        if r["v"] is None:
            mid = "".join(f"<td {grey}>n/a</td>" for _ in range(4))
            o = b = None
        else:
            v = r["v"][t]
            colour = ed.PURPLE if v < -EPS else ed.NAVY
            o, b = offer[t], bid[t]
            mid = (f"<td>{-v:,.2f}</td>"
                   f'<td style="color:{colour};font-weight:700">{v:,.2f}</td>'
                   f"<td>{b:,.2f}</td><td>{o:,.2f}</td>")
        rows += (f"<tr><th>t{t + 1}</th><td>{_num(lam[t])}</td>"
                 f"<td>{r['Pch'][t]:,.1f}</td><td>{r['Pdis'][t]:,.1f}</td>"
                 f"<td>{r['E'][t]:,.2f}</td>{mid}"
                 f"<td>{_decision(t, lam[t], r, bat, o, b)}</td></tr>")
    return f'<div class="ed-table"><table><tr>{head}</tr>{rows}</table></div>'


def _axis(title, **extra):
    return dict(title=dict(text=title, font=ed.CHART_FONT), tickfont=ed.TICK_FONT,
                gridcolor=ed.SILVER, zerolinecolor=ed.SILVER, **extra)


def _layout(fig, title, height=400):
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=ed.NAVY)),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=14, color=ed.NAVY), orientation="h", y=-0.25),
        height=height, margin=dict(t=60, b=60, l=70, r=70),
    )


def _price_chart(lam, r, bat, baseline=None) -> go.Figure:
    ts = list(range(1, len(lam) + 1))
    fig = go.Figure()
    if baseline is not None:
        fig.add_trace(go.Scatter(
            x=ts, y=baseline, mode="lines", line=dict(color=ed.MUTED, width=3, dash="dot"),
            line_shape="hv", name=f"{LAMBDA} without the battery"))
    fig.add_trace(go.Scatter(
        x=ts, y=lam, mode="lines", line=dict(color=ed.NAVY, width=4), line_shape="hv",
        name=f"{LAMBDA}{SUB_T}"))
    offer, bid = effective(r["v"], bat)
    if offer is not None:
        fig.add_trace(go.Scatter(
            x=ts, y=offer, mode="lines", line=dict(color=ed.PURPLE, width=3),
            name="effective offer c + v/η"))
        fig.add_trace(go.Scatter(
            x=ts, y=bid, mode="lines", line=dict(color=ed.PURPLE, width=3, dash="dash"),
            name="effective bid b + ηv"))
    dis = [t for t in ts if r["Pdis"][t - 1] > EPS]
    ch = [t for t in ts if r["Pch"][t - 1] > EPS]
    fig.add_trace(go.Scatter(
        x=dis, y=[lam[t - 1] for t in dis], mode="markers", name="discharging",
        marker=dict(color=ed.PURPLE, size=16, line=dict(color=ed.NAVY, width=2))))
    fig.add_trace(go.Scatter(
        x=ch, y=[lam[t - 1] for t in ch], mode="markers", name="charging",
        marker=dict(color="#FFFFFF", size=16, line=dict(color=ed.PURPLE, width=3))))
    fig.update_layout(xaxis=_axis("interval t", dtick=1), yaxis=_axis(f"{LAMBDA} ($/MWh)"))
    _layout(fig, f"{LAMBDA}{SUB_T} against the battery's effective offer and bid")
    return fig


def _power_chart(r, bat) -> go.Figure:
    ts = list(range(1, len(r["E"]) + 1))
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=ts, y=r["Pdis"], name=f"P{SUB_T}ᵈⁱˢ (MW)",
                         marker_color=ed.PURPLE))
    fig.add_trace(go.Bar(x=ts, y=-r["Pch"], name=f"−P{SUB_T}ᶜʰ (MW)",
                         marker_color=ed.NAVY))
    fig.add_trace(go.Scatter(
        x=[0.5] + ts, y=[bat["E0"]] + list(r["E"]), mode="lines+markers",
        line=dict(color=ed.NAVY, width=3), marker=dict(size=8),
        name=f"E{SUB_T} (MWh)"), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=[0.5, ts[-1]], y=[bat["E"]] * 2, mode="lines",
        line=dict(color=ed.MUTED, width=2, dash="dash"), name="Ē"), secondary_y=True)
    fig.update_layout(barmode="relative", xaxis=_axis("interval t", dtick=1),
                      yaxis=_axis("power (MW)"))
    fig.update_yaxes(title=dict(text="stored energy (MWh)", font=ed.CHART_FONT),
                     tickfont=ed.TICK_FONT, secondary_y=True, showgrid=False,
                     range=[0, max(bat["E"], 1) * 1.15])
    _layout(fig, "Charging, discharging and the tank")
    return fig


def _chain(base, probe, lam, bat) -> list[str]:
    """Plain-language diff of two battery solutions, one line per movement."""
    lines = []
    for s in range(len(lam)):
        d_dis = probe["Pdis"][s] - base["Pdis"][s]
        d_ch = probe["Pch"][s] - base["Pch"][s]
        if abs(d_dis) > 1e-4:
            gain = d_dis * DT * (lam[s] - bat["c"])
            verb = "is sold" if d_dis > 0 else "is no longer sold"
            lines.append(
                f"- {abs(d_dis) * DT:.2f} MWh at the meter {verb} in t = {s + 1}: "
                f"{abs(d_dis) * DT:.2f} × ({_num(lam[s])} − {_num(bat['c'])}) "
                f"= {gain:+.2f} $.")
        if abs(d_ch) > 1e-4:
            gain = -d_ch * DT * (lam[s] - bat["b"])
            verb = "less is bought" if d_ch < 0 else "more is bought"
            lines.append(
                f"- {abs(d_ch) * DT:.2f} MWh {verb} in t = {s + 1} at {_num(lam[s])} "
                f"against a bid of {_num(bat['b'])}: {gain:+.2f} $.")
    return lines


def _settlement(off, on) -> str:
    gens = ed.GENERATORS
    items = [("Generation cost Σ cₖ Pₖ,ₜ ΔT", off["gen_cost"], on["gen_cost"]),
             (f"Consumer payment Σ {LAMBDA}{SUB_T} D{SUB_T} ΔT", off["consumers"], on["consumers"])]
    items += [(f"{g.name} rent Σ ({LAMBDA}{SUB_T} − {_num(g.offer)}) P ΔT",
               off["rents"][k], on["rents"][k]) for k, g in enumerate(gens)]
    items.append(("Battery cash", 0.0, on["cash"]))
    rows = "".join(
        f"<tr><th>{label}</th><td>{ed.money(a)}</td><td>{ed.money(b)}</td>"
        f'<td style="color:{ed.PURPLE if abs(b - a) > 0.005 else ed.NAVY};font-weight:700">'
        f"{b - a:+,.2f}</td></tr>" for label, a, b in items)
    return ('<div class="ed-table"><table><tr><th>$ over the hour</th>'
            "<th>without battery</th><th>with battery</th><th>change</th></tr>"
            f"{rows}</table></div>")


def _send_to_price_path(lam) -> None:
    st.session_state.update(dict(zip(LAM_KEYS, [round(float(x), 2) for x in lam])))
    st.session_state["boc_mode"] = "Price path"


# --- The page -------------------------------------------------------------

def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "The battery offers what it gives up",
        "Every interval the optimiser writes a price for the energy inside the "
        "tank. That price, corrected for losses, is the battery's real offer.",
    )

    mode = st.radio("Mode", ["Price path", "Market"], horizontal=True, key="boc_mode",
                    help="Price path: the battery is a price taker facing a given "
                         "λ. Market: the three Topic 5 generators and the "
                         "battery inside the operator's problem.")
    market_mode = mode == "Market"

    st.subheader("Presets")
    presets = MARKET_PRESETS if market_mode else PRICE_PRESETS
    for column, (label, values) in zip(st.columns(len(presets)), presets.items()):
        column.button(label, key=f"boc_preset_{label}", width="stretch",
                      on_click=lambda v=values: st.session_state.update(v))

    st.subheader("Battery")
    c1, c2, c3, c4 = st.columns(4)
    c1.slider("P̄ (MW)", 0, 600, step=10, key="boc_P")
    c2.slider("Ē (MWh)", 0, 200, step=1, key="boc_E")
    c3.number_input("E₀ (MWh)", min_value=0.0, max_value=200.0, step=1.0, key="boc_E0")
    end_on = c4.checkbox("Terminal energy E₁₂ ≥ Eₑₙₔ", key="boc_end_on")
    c4.number_input("Eₑₙₔ (MWh)", min_value=0.0, max_value=200.0, step=1.0,
                    key="boc_end", disabled=not end_on)
    c1, c2, c3, c4 = st.columns(4)
    c1.number_input("ηᶜʰ", min_value=0.50, max_value=1.00, step=0.01, key="boc_eta_c")
    c2.number_input("ηᵈⁱˢ", min_value=0.50, max_value=1.00, step=0.01, key="boc_eta_d")
    c3.number_input("Charge bid bᶜʰ ($/MWh)", step=1.0, key="boc_b")
    c4.number_input("Discharge offer cᵈⁱˢ ($/MWh)", step=1.0, key="boc_c")
    binary = st.toggle("Enforce one tap at a time", key="boc_binary",
                       help="Adds the binary uₜ so the battery cannot charge "
                            "and discharge in the same interval.")

    bat = dict(P=float(st.session_state["boc_P"]), E=float(st.session_state["boc_E"]),
               E0=float(st.session_state["boc_E0"]),
               eta_c=float(st.session_state["boc_eta_c"]),
               eta_d=float(st.session_state["boc_eta_d"]),
               b=float(st.session_state["boc_b"]), c=float(st.session_state["boc_c"]))
    e_end = float(st.session_state["boc_end"]) if end_on else None

    baseline = None
    if market_mode:
        st.subheader("Demand Dₜ (MW)")
        cols = st.columns(6)
        demands = [float(cols[t % 6].number_input(
            f"t{t + 1}", min_value=0, max_value=4000, step=10, key=DEMAND_KEYS[t]))
            for t in range(T)]
        bat_off = st.toggle("Battery off", key="boc_bat_off",
                            help="Solve the market without the battery.")
        baseline = market(demands, dict(bat, P=0.0, E=0.0))
        if not baseline["ok"]:
            ed.note("**No dispatch.** Demand cannot be met inside the generator limits.")
            return
        r = baseline if bat_off else market(demands, bat, binary=binary, e_end=e_end)
        if not r["ok"]:
            ed.note("**No dispatch.** The battery limits, the terminal energy and "
                    "the demands cannot all be met at once.")
            return
        lam = r["lam"]
        baseline_lam = baseline["lam"]
    else:
        st.subheader(f"Price path {LAMBDA}{SUB_T} ($/MWh)")
        cols = st.columns(6)
        lam = [float(cols[t % 6].number_input(
            f"t{t + 1}", min_value=-1000, max_value=20000, step=1, key=LAM_KEYS[t]))
            for t in range(T)]
        r = battery_block(lam, bat, binary=binary, e_end=e_end)
        if not r["ok"]:
            ed.note("**No schedule.** The tank cannot get from E₀ to the "
                    "terminal energy inside its limits.")
            return
        baseline_lam = None

    st.plotly_chart(_price_chart(lam, r, bat, baseline_lam), width="stretch")
    st.caption("The battery is marginal only where λ meets its effective offer "
               "or bid. Neither number is in its bid; the tank puts them there.")
    st.plotly_chart(_power_chart(r, bat), width="stretch")

    st.subheader("Every interval")
    st.markdown(_table(lam, r, bat), unsafe_allow_html=True)
    st.caption("v is the value of one more megawatt-hour inside the tank. It is "
               "positive when that energy has somewhere profitable to go, zero when "
               "it has nowhere to go, and negative when it is in the way. In GAMS it "
               "is minus the marginal on the SOE row.")
    if binary:
        st.caption("One tap at a time is a mixed-integer problem, and a MILP has no "
                   "multipliers: soe.m, v and the effective columns are not defined.")
    else:
        tied = {}
        for t in range(T):
            act = "ch" if r["Pch"][t] > EPS else "dis" if r["Pdis"][t] > EPS else None
            if act:
                tied.setdefault((round(lam[t], 6), act), []).append(t)
        if any(len(ts) > 1 and any(
                (r["Pch"] if act == "ch" else r["Pdis"])[t] < bat["P"] - EPS for t in ts)
               for (_, act), ts in tied.items()):
            st.caption("This split is one of several optimal tie-breaks; the "
                       "multipliers, cash and cost are the same for all of them.")

    if market_mode:
        st.button("Send these prices to price path mode", key="boc_send",
                  on_click=_send_to_price_path, args=(lam,))
        st.caption("The probes run on the battery block priced at λ. Send this "
                   "market's λ across and the battery sees the same prices.")
    elif binary:
        st.caption("The probes need multipliers, so they run with the one-tap "
                   "toggle off.")
    else:
        _probes(lam, r, bat, e_end)

    _cash(lam, r, bat, baseline if market_mode else None)

    taps = both_taps(r)
    lp = r if not binary else (
        market(demands, bat, e_end=e_end) if market_mode else battery_block(lam, bat, e_end=e_end))
    lp_taps = both_taps(lp) if lp["ok"] else []
    if taps or lp_taps:
        items = "\n".join(
            f"- t = {t + 1}: Pᶜʰ = {lp['Pch'][t]:.1f} MW and Pᵈⁱˢ = "
            f"{lp['Pdis'][t]:.1f} MW. Energy destroyed: "
            f"{bat['eta_c'] * lp['Pch'][t] * DT:.2f} − {lp['Pdis'][t] * DT / bat['eta_d']:.2f} "
            f"= {bat['eta_c'] * lp['Pch'][t] * DT - lp['Pdis'][t] * DT / bat['eta_d']:.2f} MWh. "
            f"Cash booked: {lam[t] * (lp['Pdis'][t] - lp['Pch'][t]) * DT:,.2f} $."
            for t in lp_taps)
        tail = (f"\n\nWith one tap enforced the declared surplus goes from "
                f"{lp['surplus']:,.2f} $ to {r['surplus']:,.2f} $."
                if binary else "\n\nTurn on **Enforce one tap at a time** above to add "
                               "the binary uₜ.")
        ed.note("**Both taps open at once.**\n\n" + items +
                "\n\nThe LP found a way to be paid for consuming energy without "
                "storing it. The physics forbids charging and discharging at once; "
                "the binary is the physics." + tail)

    with st.expander("The formulation"):
        st.markdown("The SOE row, with multiplier $\\theta_t$, and the value of stored energy:")
        st.latex(r"E_t = E_{t-1} + \eta^{ch} P^{ch}_t \, \Delta T - \frac{P^{dis}_t \, \Delta T}{\eta^{dis}}, "
                 r"\qquad v_t = -\theta_t")
        st.markdown("Price path mode, the battery block priced at $\\lambda$:")
        st.latex(r"\min \sum_t \left[ (\lambda_t - b^{ch}) P^{ch}_t + (c^{dis} - \lambda_t) P^{dis}_t \right] \Delta T")
        st.markdown("Market mode, the operator's problem:")
        st.latex(r"\min \sum_t \Big[ \sum_k c_k P_{k,t} + c^{dis} P^{dis}_t - b^{ch} P^{ch}_t \Big] \Delta T")
        st.latex(r"\text{s.t.} \quad \sum_k P_{k,t} + P^{dis}_t - P^{ch}_t = D_t \quad (\lambda_t \, \Delta T), "
                 r"\qquad 0 \le P_{k,t} \le \bar{P}_k")
        st.latex(r"0 \le P^{ch}_t \le \bar{P}, \quad 0 \le P^{dis}_t \le \bar{P}, \quad 0 \le E_t \le \bar{E}, "
                 r"\quad E_{12} \ge E_{end}")
        st.markdown("First-order conditions where the battery is strictly inside its limits:")
        st.latex(r"\text{discharging:} \quad \lambda_t = c^{dis} + \frac{v_t}{\eta^{dis}}, "
                 r"\qquad \text{charging:} \quad \lambda_t = b^{ch} + \eta^{ch} v_t")
        st.markdown("One tap at a time, with binary $u_t$:")
        st.latex(r"P^{ch}_t \le \bar{P} u_t, \qquad P^{dis}_t \le \bar{P} (1 - u_t), \qquad u_t \in \{0, 1\}")


def _probes(lam, r, bat, e_end) -> None:
    st.subheader("What is one megawatt-hour worth at t?")
    left, right = st.columns([1, 2])
    t = left.selectbox("Interval t", options=list(range(1, T + 1)),
                       format_func=lambda i: f"t{i}", key="boc_probe_t") - 1
    kind = right.radio("Probe", ["inject", "force"], key="boc_probe_kind", horizontal=True,
                       format_func=lambda k: {
                           "inject": "Add one megawatt-hour to the tank at t",
                           "force": "Force one extra MW of discharge at t"}[k])
    if kind == "inject":
        probe = battery_block(lam, bat, e_end=e_end, inject=(t, 1.0))
        if not probe["ok"]:
            ed.note("The extra megawatt-hour cannot be placed: the tank has no "
                    "room and no way to make any.")
            return
        delta = probe["surplus"] - r["surplus"]
        st.markdown(f"Adding 1 MWh to the right-hand side of the SOE row at t = {t + 1} "
                    f"changes the declared surplus by **{delta:+.2f} $**, and "
                    f"$v_{{{t + 1}}} = {r['v'][t]:.2f}$. Same number, as it must be.")
        lines = _chain(r, probe, lam, bat)
        if r["E"][t] >= bat["E"] - EPS and r["Pch"][t] < EPS:
            st.markdown(f"The tank is full at t = {t + 1} and nothing is being bought "
                        "there, so the extra megawatt-hour can only be sold now: "
                        f"$(\\lambda_t - c^{{dis}}) \\, \\eta^{{dis}}$. The value of a "
                        "bigger tank here is $v_{later} - v_{now}$.")
        st.markdown("\n".join(lines) if lines else "- Nothing moves: the extra energy "
                                                    "sits in the tank unused.")
    else:
        probe = battery_block(lam, bat, e_end=e_end, force_dis=(t, r["Pdis"][t] + 1.0))
        if r["Pdis"][t] + 1.0 > bat["P"] + EPS or not probe["ok"]:
            ed.note(f"One more MW of discharge at t = {t + 1} is not feasible: the "
                    "tap is already at its limit or the tank cannot supply it.")
            return
        delta = probe["surplus"] - r["surplus"]
        st.markdown(f"Fixing $P^{{dis}}_{{{t + 1}}}$ at {r['Pdis'][t]:.1f} + 1 MW changes "
                    f"the declared surplus by **{delta:+.2f} $**.")
        lines = _chain(r, probe, lam, bat)
        st.markdown("\n".join(lines) if lines else "- Nothing else moves.")
        if abs(delta) < 0.005:
            st.caption("The change is 0.00 $: the displaced interval has the same "
                       "price as this one, so this probe is uninformative here. It "
                       "says something only when the prices differ.")


def _cash(lam, r, bat, baseline) -> None:
    st.subheader("Cash")
    ratio, threshold, passes = round_trip(lam, bat)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        ed.headline("MWh bought", f"{r['bought']:,.2f}")
    with c2:
        ed.headline("MWh sold", f"{r['sold']:,.2f}")
    with c3:
        ed.headline(r"Battery cash (\$)", ed.money(r["cash"]))
    with c4:
        ed.headline(r"Declared surplus (\$)", ed.money(r["surplus"]))
    with c5:
        ed.headline(r"$\lambda_{high} / \lambda_{low}$",
                    "n/a" if ratio is None else f"{ratio:.3f} {'pass' if passes else 'fail'}")
    st.markdown(r"Battery cash is $\sum_t \lambda_t (P^{dis}_t - P^{ch}_t) \Delta T$; the "
                r"declared surplus is minus the objective of the battery block. The round-trip "
                rf"test is $\lambda_{{high}} / \lambda_{{low}} > 1 / (\eta^{{ch}} \eta^{{dis}}) "
                rf"= {threshold:.3f}$.")
    if ratio is not None and not passes:
        ed.note("The operator dispatched the bid, not the physics. The round-trip loss "
                "is the battery's own problem.")
    if baseline is not None:
        st.subheader("Settlement, with and without the battery")
        st.markdown(_settlement(baseline, r), unsafe_allow_html=True)
        if any(abs(a - b) > 0.005 for a, b in zip(baseline["lam"], lam)):
            ed.note("A battery large enough to move the charging price raises what "
                    "every consumer pays in those intervals and what every other "
                    "generator earns. Cost, payment and rent are three different objects.")
