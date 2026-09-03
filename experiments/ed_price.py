"""Single-interval economic dispatch price explorer (Topic 5, block two).

The classroom instrument for the lambda staircase and complementary slackness:
one demand slider, and everything else on the page is what the LP says about
it. Driven live in the Topic 5 Review Forum, so it must read at Zoom distance
and open correctly from a cold deep link.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from experiments._kit import ed

DEMAND_KEY = "edp_demand"
MIN_KEYS = ("edp_min1", "edp_min2", "edp_min3")

DEFAULTS = {DEMAND_KEY: 2600, MIN_KEYS[0]: 0, MIN_KEYS[1]: 0, MIN_KEYS[2]: 0}

# The two cases the forum runs live. A preset is just the widget values, so it
# applies by writing session state in the button callback, before the sliders
# are rebuilt on the rerun.
PRESETS = {
    "Case 1: D = 2600": {DEMAND_KEY: 2600, MIN_KEYS[0]: 0,
                         MIN_KEYS[1]: 0, MIN_KEYS[2]: 0},
    "Forced on: G1 minimum 500, D = 600": {DEMAND_KEY: 600, MIN_KEYS[0]: 500,
                                           MIN_KEYS[1]: 0, MIN_KEYS[2]: 0},
}


def _position(power: float, minimum: float, capacity: float) -> str:
    if power >= capacity - 1e-6:
        return "at max"
    if power <= minimum + 1e-6:
        return "at min"
    return "inside its limits"


def _staircase_chart(minimums, demand: float, price: float | None) -> go.Figure:
    segments = ed.staircase(minimums)
    fig = go.Figure()
    for i, (lo, hi, offer) in enumerate(segments):
        fig.add_trace(go.Scatter(
            x=[lo, hi], y=[offer, offer], mode="lines",
            line=dict(color=ed.NAVY, width=5),
            name="lambda", showlegend=i == 0,
            hovertemplate="D = %{x:.0f} MW, lambda = %{y:.0f} $/MWh<extra></extra>",
        ))
        if i:  # the riser between this tread and the one below it
            fig.add_trace(go.Scatter(
                x=[lo, lo], y=[segments[i - 1][2], offer], mode="lines",
                line=dict(color=ed.NAVY, width=5, dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    top = segments[-1][1] if segments else ed.TOTAL_CAPACITY
    fig.add_vrect(x0=top, x1=4200, fillcolor=ed.LIMESTONE, opacity=0.9,
                  line_width=0, layer="below")
    fig.add_annotation(x=(top + 4200) / 2, y=35, text="infeasible",
                       showarrow=False, font=dict(size=16, color=ed.MUTED))

    if price is not None:
        fig.add_trace(go.Scatter(
            x=[demand], y=[price], mode="markers",
            marker=dict(color=ed.PURPLE, size=22, line=dict(color=ed.NAVY, width=3)),
            name="you are here",
            hovertemplate="D = %{x:.0f} MW, lambda = %{y:.0f} $/MWh<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Lambda against demand", font=dict(size=20, color=ed.NAVY)),
        xaxis=dict(title=dict(text="Demand D (MW)", font=ed.CHART_FONT),
                   tickfont=ed.TICK_FONT, range=[0, 4200],
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER),
        yaxis=dict(title=dict(text="lambda ($/MWh)", font=ed.CHART_FONT),
                   tickfont=ed.TICK_FONT, range=[0, 60],
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=16, color=ed.NAVY)),
        height=420, margin=dict(t=60, b=60, l=70, r=30),
    )
    return fig


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "Economic dispatch: where the price comes from",
        "One five-minute interval, three generators, one demand. Move demand "
        "and watch which generator is setting lambda, and what the capacity "
        "multipliers have to be for the first-order condition to hold.",
    )

    st.subheader("Preset cases")
    for column, (label, values) in zip(st.columns(len(PRESETS)), PRESETS.items()):
        column.button(
            label, key=f"edp_preset_{label}", width="stretch",
            on_click=lambda v=values: st.session_state.update(v),
        )

    demand = st.slider(
        "Demand D (MW)", min_value=0, max_value=4200, step=1, key=DEMAND_KEY,
        help="One five-minute interval. Delta T = 1/12 h.",
    )

    with st.expander("Advanced: minimum loads"):
        st.markdown(
            '<div class="ed-wrap"><p>A minimum load forces a generator on '
            "even when its offer is above lambda. That is what puts a "
            "non-zero mu-underbar on the row.</p></div>",
            unsafe_allow_html=True,
        )
        minimums = [
            st.number_input(
                f"{gen.name} minimum load (MW)", min_value=0,
                max_value=int(gen.capacity), step=10, key=MIN_KEYS[k],
            )
            for k, gen in enumerate(ed.GENERATORS)
        ]

    minimums = [float(m) for m in minimums]
    result = ed.solve([float(demand)], minimums)

    if not result.ok:
        ed.note(f"<strong>No dispatch.</strong> {result.message}")
        st.plotly_chart(_staircase_chart(minimums, demand, None), width="stretch")
        return

    power = result.P[0]
    lam = result.lam[0]
    cost = result.cost[0]

    columns = st.columns([1.2, 1, 1, 1, 1.3])
    columns[0].markdown(ed.headline("Price lambda", f"{lam:,.2f}", "$/MWh"),
                        unsafe_allow_html=True)
    for k, gen in enumerate(ed.GENERATORS):
        columns[k + 1].markdown(
            ed.headline(f"{gen.name} dispatch", f"{power[k]:,.0f}", "MW"),
            unsafe_allow_html=True,
        )
    columns[4].markdown(
        ed.headline("Offered cost", ed.money(cost), "$ per five-minute interval"),
        unsafe_allow_html=True,
    )

    st.plotly_chart(_staircase_chart(minimums, demand, lam), width="stretch")

    st.subheader("Capacity multipliers and the first-order condition")
    st.markdown(
        '<div class="ed-wrap"><p>For every generator, '
        "lambda = c_k + mu-bar_k - mu-underbar_k. A multiplier is the marginal "
        "value of relaxing that constraint by one MW, in $/MWh. The row "
        "highlighted in lavender is the generator setting the price.</p></div>",
        unsafe_allow_html=True,
    )
    for k, gen in enumerate(ed.GENERATORS):
        position = _position(power[k], minimums[k], gen.capacity)
        mu_up = result.mu_max[0][k]
        mu_dn = result.mu_min[0][k]
        marginal = position == "inside its limits"
        st.markdown(
            f'<div class="ed-row{" marginal" if marginal else ""}">'
            f'<span class="who">{gen.name}</span> offers {gen.offer:,.0f} $/MWh, '
            f"dispatched {power[k]:,.0f} MW, <strong>{position}</strong>"
            f"{' and setting the price' if marginal else ''}.<br>"
            f"mu-bar = {mu_up:,.2f} $/MWh, mu-underbar = {mu_dn:,.2f} $/MWh<br>"
            f'<span class="foc">lambda = c_{k + 1} + mu-bar_{k + 1} - '
            f"mu-underbar_{k + 1}&nbsp; = &nbsp;{gen.offer:,.2f} + {mu_up:,.2f} "
            f"- {mu_dn:,.2f} = {lam:,.2f} $/MWh</span></div>",
            unsafe_allow_html=True,
        )

    st.subheader("The one-megawatt test")
    st.markdown(
        '<div class="ed-wrap"><p>Solve again one MW either side and read the '
        "change in offered cost. That change, in $/h, is what the price is "
        "meant to be.</p></div>",
        unsafe_allow_html=True,
    )

    def _side(delta: int):
        probe = ed.solve([float(demand + delta)], minimums)
        if not probe.ok:
            return None
        return (probe.cost[0] - cost) * ed.PER_HOUR * (1 if delta > 0 else -1)

    above = _side(+1)
    below = _side(-1)
    left, right = st.columns(2)
    left.markdown(
        ed.headline("Serving one MW less (D - 1)",
                    "not feasible" if below is None else f"{below:,.2f}", "$/h"),
        unsafe_allow_html=True,
    )
    right.markdown(
        ed.headline("Serving one MW more (D + 1)",
                    "not feasible" if above is None else f"{above:,.2f}", "$/h"),
        unsafe_allow_html=True,
    )

    disagree = (
        above is None or below is None or abs(above - below) > 1e-6
    )
    if disagree:
        ed.note(
            "<strong>The two sides disagree. The price is not unique here.</strong>"
            " Demand sits exactly on a riser of the staircase, so the cost of the "
            "next MW and the saving from the last MW are set by different "
            "generators. Any value between the two clears the market."
        )
    else:
        ed.note(
            f"Both sides agree at {above:,.2f} $/h, which is lambda. The price "
            "is the cost of the next megawatt."
        )
