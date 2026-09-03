"""Why a price-taking generator offers its true cost (Topic 5 self-study).

Links back to the Part III incentive argument and to the producer-surplus story
from Module 1. Not driven live in the review forum: this one is reached from
Canvas and worked through alone.

The student owns G4 and controls one thing, its offer. G4 is too small to move
lambda, so the payment it receives is fixed by the other three generators and
the only thing its own offer decides is whether it runs.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from experiments._kit import ed

OFFER_KEY = "tro_offer"
SCENARIO_KEY = "tro_scenario"

G4_COST = 45.0  # $/MWh, the true cost of the unit the student owns
G4_CAPACITY = 50.0  # MW

HIGH = "High demand day"
MILD = "Mild day"
SCENARIOS = {HIGH: 2600.0, MILD: 2200.0}

DEFAULTS = {OFFER_KEY: 45.0, SCENARIO_KEY: HIGH}


def _profit(offer: float, price: float) -> float | None:
    """Profit in $/h. None when the offer sits exactly on the price."""
    if abs(offer - price) < 1e-9:
        return None
    if offer < price:
        return (price - G4_COST) * G4_CAPACITY
    return 0.0


def _profit_chart(price: float, offer: float) -> go.Figure:
    """Profit against offer: dispatched below lambda, idle above it."""
    inside = (price - G4_COST) * G4_CAPACITY
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[0, price], y=[inside, inside], mode="lines",
        line=dict(color=ed.NAVY, width=5), name=f"offer at or below {ed.LAMBDA}",
        hovertemplate="offer %{x:.0f} $/MWh, profit %{y:,.0f} $/h<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[price, price], y=[inside, 0.0], mode="lines",
        line=dict(color=ed.NAVY, width=5, dash="dot"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[price, 100], y=[0.0, 0.0], mode="lines",
        line=dict(color=ed.MUTED, width=5), name=f"offer above {ed.LAMBDA}",
        hovertemplate="offer %{x:.0f} $/MWh, profit %{y:,.0f} $/h<extra></extra>",
    ))
    profit = _profit(offer, price)
    fig.add_trace(go.Scatter(
        x=[offer], y=[0.0 if profit is None else profit], mode="markers",
        marker=dict(color=ed.PURPLE, size=22, line=dict(color=ed.NAVY, width=3)),
        name="your offer",
        hovertemplate="your offer %{x:.0f} $/MWh<extra></extra>",
    ))
    fig.add_vline(x=G4_COST, line=dict(color=ed.PURPLE, width=3, dash="dash"))
    fig.add_annotation(x=G4_COST, y=inside, yshift=22,
                       text="your true cost, 45 $/MWh", showarrow=False,
                       font=dict(size=16, color=ed.PURPLE))

    fig.update_layout(
        title=dict(text="Profit against your offer",
                   font=dict(size=20, color=ed.NAVY)),
        xaxis=dict(title=dict(text="Your offer for G4 ($/MWh)", font=ed.CHART_FONT),
                   tickfont=ed.TICK_FONT, range=[0, 100],
                   gridcolor=ed.SILVER, zerolinecolor=ed.SILVER),
        yaxis=dict(title=dict(text="Profit ($/h)", font=ed.CHART_FONT),
                   tickfont=ed.TICK_FONT, range=[-400, 400],
                   gridcolor=ed.SILVER, zerolinecolor=ed.MUTED),
        font=ed.CHART_FONT, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        legend=dict(font=dict(size=16, color=ed.NAVY)),
        height=430, margin=dict(t=60, b=60, l=80, r=30),
    )
    return fig


def render() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)

    ed.header(
        "Offering your true cost",
        r"You own $G_4$: true cost $c_4 = 45$ \$/MWh, capacity 50 MW. $G_1$, "
        r"$G_2$ and $G_3$ set $\lambda$ between them, and at 50 MW your unit "
        r"is far too small to move it. Your offer decides one thing only, "
        r"whether $G_4$ is dispatched.",
    )

    st.subheader("Pick the day")
    for column, name in zip(st.columns(len(SCENARIOS)), SCENARIOS):
        column.button(
            name, key=f"tro_pick_{name}", width="stretch",
            on_click=lambda n=name: st.session_state.update({SCENARIO_KEY: n}),
        )

    scenario = st.session_state[SCENARIO_KEY]
    demand = SCENARIOS[scenario]
    price = ed.price_at(demand)

    offer = st.slider(
        "Your offer for G4 ($/MWh)", min_value=0.0, max_value=100.0, step=1.0,
        key=OFFER_KEY,
    )

    profit = _profit(offer, price)
    dispatched = profit is not None and offer < price

    columns = st.columns(3)
    with columns[0]:
        ed.headline(f"{scenario}: demand $D$ (MW)", f"{demand:,.0f}")
    with columns[1]:
        ed.headline(r"Price $\lambda$ (\$/MWh)", f"{price:,.2f}")
    with columns[2]:
        if profit is None:
            ed.headline(r"$G_4$ outcome", "marginal")
        else:
            ed.headline(r"$G_4$ profit $\pi$ (\$/h)", f"{profit:+,.0f}")

    st.markdown("Your profit for the hour is")
    st.latex(
        r"\pi = \begin{cases}"
        r"(\lambda - c_4)\,\bar{P}_4 & \text{if your offer} \le \lambda \\[2pt]"
        r"0 & \text{otherwise}"
        r"\end{cases}"
    )

    if profit is None:
        ed.note(
            "**Marginal: dispatch is a coin toss, profit is zero either way.** "
            r"Your offer sits exactly on $\lambda$, so being dispatched pays "
            rf"you ${price:,.0f}$ \$/MWh for energy that costs you "
            rf"${price:,.0f}$ \$/MWh to make."
        )
    elif dispatched:
        ed.note(
            rf"**$G_4$ is dispatched** at $\bar{{P}}_4 = {G4_CAPACITY:,.0f}$ MW, "
            rf"paid $\lambda = {price:,.2f}$ \$/MWh against a true cost of "
            rf"$c_4 = {G4_COST:,.0f}$ \$/MWh, so "
            rf"$\pi = ({price:,.0f} - {G4_COST:,.0f}) \times "
            rf"{G4_CAPACITY:,.0f} = {profit:+,.0f}$ \$/h."
            + ("" if profit >= 0 else " That is a loss, and you offered your "
               "way into it.")
        )
    else:
        ed.note(
            r"**$G_4$ is not dispatched.** Your offer is above $\lambda$, so "
            r"the market passes you over and $\pi = 0$ \$/h."
            + (" On this day that is the right outcome: running would have "
               "lost you money." if price < G4_COST else
               r" On this day you have just given up $250$ \$/h you could "
               "have had.")
        )

    st.plotly_chart(_profit_chart(price, offer), width="stretch")

    ed.note(
        "Offering your true cost is never worse than any other offer, on "
        "either day. Offer low and you can be dispatched at a loss; offer high "
        "and you forfeit profitable dispatch. Payment does not depend on your "
        "own offer, only dispatch does."
    )

    st.subheader("The two days side by side")
    for name, day_demand in SCENARIOS.items():
        day_price = ed.price_at(day_demand)
        margin = (day_price - G4_COST) * G4_CAPACITY
        runs = day_price > G4_COST
        ed.row(
            rf"**{name}**: $D = {day_demand:,.0f}$ MW, so "
            rf"$\lambda = {day_price:,.0f}$ \$/MWh. Offering $c_4 = 45$ \$/MWh "
            rf"{'runs' if runs else 'keeps off'} $G_4$ and earns "
            rf"${max(margin, 0.0):+,.0f}$ \$/h. "
            + ("Offering above $\\lambda$ would forfeit that." if runs else
               rf"Offering below $\lambda$ would run it at ${margin:+,.0f}$ \$/h.")
        )
