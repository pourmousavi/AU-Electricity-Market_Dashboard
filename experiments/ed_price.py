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
            name=f"{ed.LAMBDA}", showlegend=i == 0,
            hovertemplate=f"D = %{{x:.0f}} MW, {ed.LAMBDA} = %{{y:.0f}} $/MWh<extra></extra>",
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
            hovertemplate=f"D = %{{x:.0f}} MW, {ed.LAMBDA} = %{{y:.0f}} $/MWh<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=f"{ed.LAMBDA} against demand D",
                   font=dict(size=20, color=ed.NAVY)),
        xaxis=dict(title=dict(text="Demand D (MW)", font=ed.CHART_FONT),
                   tickfont=ed.TICK_FONT, range=[0, 4200],
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER),
        yaxis=dict(title=dict(text=f"{ed.LAMBDA} ($/MWh)", font=ed.CHART_FONT),
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
        r"and watch which generator sets $\lambda$, and what the capacity "
        r"multipliers $\bar{\mu}_k$ and $\underline{\mu}_k$ have to be for the "
        "first-order condition to hold.",
    )

    st.subheader("Preset cases")
    for column, (label, values) in zip(st.columns(len(PRESETS)), PRESETS.items()):
        column.button(
            label, key=f"edp_preset_{label}", width="stretch",
            on_click=lambda v=values: st.session_state.update(v),
        )

    demand = st.slider(
        "Demand D (MW)", min_value=0, max_value=4200, step=1, key=DEMAND_KEY,
    )
    st.caption(r"One dispatch interval, so $\Delta T = 1/12$ h.")

    with st.expander("Advanced: minimum loads"):
        st.markdown(
            r"A minimum load forces a generator on even when its offer is "
            r"above $\lambda$. That is what puts a non-zero "
            r"$\underline{\mu}_k$ on the row."
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
        ed.note(f"**No dispatch.** {result.message}")
        st.plotly_chart(_staircase_chart(minimums, demand, None), width="stretch")
        return

    power = result.P[0]
    lam = result.lam[0]
    cost = result.cost[0]

    columns = st.columns([1.2, 1, 1, 1, 1.4])
    with columns[0]:
        ed.headline(r"Price $\lambda$ (\$/MWh)", f"{lam:,.2f}")
    for k, gen in enumerate(ed.GENERATORS):
        with columns[k + 1]:
            ed.headline(rf"${gen.name}$: $P_{k + 1}$ (MW)", f"{power[k]:,.0f}")
    with columns[4]:
        ed.headline(r"Offered cost (\$ per five-minute interval)",
                    ed.money(cost))

    st.plotly_chart(_staircase_chart(minimums, demand, lam), width="stretch")

    st.subheader("Capacity multipliers and the first-order condition")
    st.markdown(
        r"For every generator $k$, the first-order condition of the dispatch "
        r"problem is"
    )
    st.latex(r"\lambda = c_k + \bar{\mu}_k - \underline{\mu}_k")
    st.markdown(
        r"where $\bar{\mu}_k$ and $\underline{\mu}_k$ are the multipliers on "
        r"the upper and lower capacity limits. Each is the marginal value of "
        r"relaxing that constraint by one MW, in \$/MWh. The row highlighted "
        r"in lavender is the generator setting the price."
    )
    for k, gen in enumerate(ed.GENERATORS):
        position = _position(power[k], minimums[k], gen.capacity)
        mu_up = result.mu_max[0][k]
        mu_dn = result.mu_min[0][k]
        marginal = position == "inside its limits"
        ed.row(
            rf"**{gen.name}** offers $c_{k + 1} = {gen.offer:,.0f}$ \$/MWh and "
            rf"is dispatched at $P_{k + 1} = {power[k]:,.0f}$ MW, "
            rf"**{position}**{' and setting the price' if marginal else ''}."
            "\n\n"
            rf"$$\lambda = c_{k + 1} + \bar{{\mu}}_{k + 1} - "
            rf"\underline{{\mu}}_{k + 1} = {gen.offer:,.2f} + {mu_up:,.2f} - "
            rf"{mu_dn:,.2f} = {lam:,.2f} \ \$/\mathrm{{MWh}}$$",
            marginal=marginal,
        )

    st.subheader("The one-megawatt test")
    st.markdown(
        r"Solve again one MW either side and read the change in offered cost. "
        r"Scaled by $1/\Delta T$ that change is in \$/h, and it is what the "
        r"price is meant to be."
    )

    def _side(delta: int):
        probe = ed.solve([float(demand + delta)], minimums)
        if not probe.ok:
            return None
        return (probe.cost[0] - cost) * ed.PER_HOUR * (1 if delta > 0 else -1)

    above = _side(+1)
    below = _side(-1)
    left, right = st.columns(2)
    with left:
        ed.headline(r"Serving one MW less, $D-1$ (\$/h)",
                    "not feasible" if below is None else f"{below:,.2f}")
    with right:
        ed.headline(r"Serving one MW more, $D+1$ (\$/h)",
                    "not feasible" if above is None else f"{above:,.2f}")

    if above is None or below is None or abs(above - below) > 1e-6:
        ed.note(
            "**The two sides disagree. The price is not unique here.** "
            r"Demand sits exactly on a riser of the staircase, so the cost of "
            r"the next MW and the saving from the last MW are set by different "
            r"generators. Any $\lambda$ between the two clears the market."
        )
    else:
        ed.note(
            rf"Both sides agree at ${above:,.2f}$ \$/h, which is $\lambda$. "
            r"The price is the cost of the next megawatt."
        )
