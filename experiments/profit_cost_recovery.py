"""Profit Cost Recovery.

Extracted from week3_pricing_market_power.py (profit_cost_recovery_section) on 2026-08-12."""

import math

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# --- Economics -------------------------------------------------------------
#
# Pure functions: numbers in, numbers out, no Streamlit. Everything the page
# displays is derived here so a student can trace any figure on screen back to
# an input, and so the model can be tested without rendering anything.

GJ_PER_MWH = 3.6
HOURS_PER_YEAR = 8760

# The plant size the quoted $/kW refers to. Scale economies are expressed
# relative to it, so at this size the figure a student types is the figure used.
REFERENCE_CAPACITY_MW = 400.0


def capital_recovery_factor(rate: float, years: int) -> float:
    """The fraction of capital that must be repaid each year.

    Turns an up-front CAPEX into the level annual payment that repays it over
    `years` while earning `rate` on the outstanding balance -- which is what
    makes an overnight cost comparable with a year of revenue.
    """
    if rate == 0:
        return 1.0 / years
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def marginal_cost(fuel_price: float, efficiency_pct: float, vom: float) -> float:
    """Short-run cost of one more MWh, in $/MWh.

    A MWh is 3.6 GJ of energy, so a plant at `efficiency_pct` burns
    3.6/efficiency GJ of fuel to deliver it.
    """
    heat_rate = GJ_PER_MWH / (efficiency_pct / 100)
    return fuel_price * heat_rate + vom


def scaled_capex_per_kw(capex_per_kw, capacity_mw, scale_exponent,
                        reference_mw=REFERENCE_CAPACITY_MW) -> float:
    """$/kW at this size, from a cost quoted at the reference size.

    Bigger plants cost less per kW: a turbine hall, a connection and a control
    room do not double when the machine does. The standard way to express that
    is an exponent on TOTAL cost, cost ∝ size^e with e below 1, which leaves
    the per-kW figure moving as size^(e-1). At e = 1 there are no scale
    economies and this returns the quoted figure unchanged at every size.
    """
    if capacity_mw <= 0 or reference_mw <= 0:
        return capex_per_kw
    return capex_per_kw * (capacity_mw / reference_mw) ** (scale_exponent - 1)


def annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw,
                      scale_exponent: float = 1.0) -> dict:
    """Annualised CAPEX and fixed O&M, each kept separate for display."""
    capacity_kw = capacity_mw * 1000
    per_kw = scaled_capex_per_kw(capex_per_kw, capacity_mw, scale_exponent)
    capex_total = per_kw * capacity_kw
    crf = capital_recovery_factor(wacc, life_years)
    annualised_capex = capex_total * crf
    fixed_om = fom_per_kw * capacity_kw
    return {
        "capex_total": capex_total,
        "crf": crf,
        "annualised_capex": annualised_capex,
        "fixed_om": fixed_om,
        "total": annualised_capex + fixed_om,
    }


def dispatch(bands, marginal_cost_value, forced_outage_rate, planned_days) -> list:
    """Hours per price band after outages, and which of them are in merit.

    The two kinds of unavailability behave differently, and the difference is
    worth seeing:

    * Forced outages are random, so they scale every band down equally.
    * Planned maintenance is scheduled, so an operator takes it in the
      cheapest hours first -- which is why maintenance costs a peaker almost
      no revenue, and why outage scheduling is an economic decision.
    """
    available = [band["hours"] * (1 - forced_outage_rate) for band in bands]

    remaining = planned_days * 24
    for index in sorted(range(len(bands)), key=lambda i: bands[i]["price"]):
        if remaining <= 0:
            break
        taken = min(available[index], remaining)
        available[index] -= taken
        remaining -= taken

    return [
        {
            "price": band["price"],
            "hours": band["hours"],
            "available_hours": hours,
            "running_hours": hours if band["price"] > marginal_cost_value else 0.0,
        }
        for band, hours in zip(bands, available)
    ]


def achieved_return(capex_total: float, annual_cash_flow: float,
                    life_years: int) -> float | None:
    """The return the capital actually earns, or None if it never repays.

    For a flat annual cash flow this is exact: find the rate whose recovery
    factor turns this CAPEX into exactly this cash flow. Bisection, because
    the closed form does not exist and the factor rises monotonically in rate.
    """
    if not math.isfinite(capex_total) or not math.isfinite(annual_cash_flow):
        return None  # defence in depth: a non-finite input must never reach bisection
    if capex_total <= 0 or annual_cash_flow <= 0:
        return None
    if annual_cash_flow * life_years <= capex_total:
        return None  # does not even return the capital, let alone a profit

    low, high = 0.0, 10.0
    for _ in range(200):
        mid = (low + high) / 2
        if capital_recovery_factor(mid, life_years) * capex_total < annual_cash_flow:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def investment_metrics(capacity_mw, life_years, capex_per_kw, wacc, fom_per_kw,
                       fuel_price, efficiency_pct, vom, forced_outage_rate,
                       planned_days, bands, scale_exponent: float = 1.0,
                       absorption_mw: float | None = None) -> dict:
    """Everything the page displays, from what the student typed.

    `absorption_mw` is the most this plant can actually sell in any hour --
    the room the market has for it. Capacity beyond that limit is built and
    maintained but never sells anything, which is what gives plant size an
    optimum rather than making bigger always better.
    """
    mc = marginal_cost(fuel_price, efficiency_pct, vom)
    fixed = annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years,
                              fom_per_kw, scale_exponent)
    dispatched = dispatch(bands, mc, forced_outage_rate, planned_days)

    sold_mw = capacity_mw if absorption_mw is None else min(capacity_mw, absorption_mw)
    running_hours = sum(band["running_hours"] for band in dispatched)
    energy = sold_mw * running_hours
    revenue = sum(band["price"] * sold_mw * band["running_hours"]
                  for band in dispatched)
    variable_cost = mc * energy
    short_run_profit = revenue - variable_cost
    long_run_profit = short_run_profit - fixed["total"]

    return {
        "marginal_cost": mc,
        "fixed": fixed,
        "dispatched": dispatched,
        "running_hours": running_hours,
        "energy": energy,
        "revenue": revenue,
        "variable_cost": variable_cost,
        "short_run_profit": short_run_profit,
        "long_run_profit": long_run_profit,
        "sold_mw": sold_mw,
        "idle_mw": capacity_mw - sold_mw,
        "capex_per_kw": fixed["capex_total"] / (capacity_mw * 1000),
        "capacity_factor": 100 * energy / (capacity_mw * HOURS_PER_YEAR),
        "required_return": wacc,
        "achieved_return": achieved_return(
            fixed["capex_total"], short_run_profit - fixed["fixed_om"], life_years
        ),
        "is_viable": long_run_profit >= 0,
    }


def create_price_duration_plot(metrics) -> go.Figure:
    """The price-duration curve, with the hours this plant runs shaded.

    This is the chart that answers "which hours pay for the plant". Bands are
    ordered dearest first, the classic price-duration shape, with marginal cost
    drawn across it: everything above the line and inside a shaded block is
    scarcity rent.
    """
    ordered = sorted(metrics["dispatched"], key=lambda band: -band["price"])
    mc = metrics["marginal_cost"]
    fig = go.Figure()

    cursor = 0.0
    xs, ys = [], []
    for band in ordered:
        xs += [cursor, cursor + band["hours"]]
        ys += [band["price"], band["price"]]
        if band["running_hours"] > 0:
            fig.add_trace(go.Scatter(
                x=[cursor, cursor + band["running_hours"],
                   cursor + band["running_hours"], cursor, cursor],
                y=[mc, mc, band["price"], band["price"], mc],
                fill="toself", fillcolor="rgba(78, 205, 196, 0.35)",
                mode="none", showlegend=False,
                hovertemplate=(
                    f"${band['price']:,.0f}/MWh for "
                    f"{band['running_hours']:,.0f} h<br>"
                    f"margin ${band['price'] - mc:,.0f}/MWh<extra></extra>"
                ),
            ))
        cursor += band["hours"]

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", name="Price-duration curve",
        line=dict(color="#1f77b4", width=3),
        hovertemplate="%{y:$,.0f}/MWh<extra></extra>",
    ))
    fig.add_hline(
        y=mc, line_dash="dash", line_color="#FF6B6B",
        annotation_text=f"marginal cost ${mc:,.0f}/MWh",
        annotation_position="top right",
    )
    fig.update_layout(
        title="When does this plant run, and what does it earn?",
        xaxis_title="Hours per year (dearest first)",
        yaxis_title="Price ($/MWh)",
        height=420, hovermode="closest",
    )
    return fig


def create_waterfall_plot(metrics) -> go.Figure:
    """Revenue down to long-run profit, one bar per real quantity."""
    fixed = metrics["fixed"]
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "total", "relative", "relative", "total"],
        x=["Revenue", "Variable cost", "Short-run profit",
           "Annualised CAPEX", "Fixed O&M", "Long-run profit"],
        y=[metrics["revenue"] / 1e6, -metrics["variable_cost"] / 1e6, 0,
           -fixed["annualised_capex"] / 1e6, -fixed["fixed_om"] / 1e6, 0],
        text=[f"${metrics['revenue']/1e6:,.1f}M",
              f"−${metrics['variable_cost']/1e6:,.1f}M",
              f"${metrics['short_run_profit']/1e6:,.1f}M",
              f"−${fixed['annualised_capex']/1e6:,.1f}M",
              f"−${fixed['fixed_om']/1e6:,.1f}M",
              f"${metrics['long_run_profit']/1e6:,.1f}M"],
        textposition="outside",
        connector={"line": {"color": "rgba(0,0,0,0.3)"}},
        increasing={"marker": {"color": "#4ECDC4"}},
        decreasing={"marker": {"color": "#FF6B6B"}},
        totals={"marker": {"color": "#1f77b4"}},
    ))
    fig.update_layout(
        title="From revenue to long-run profit",
        yaxis_title="$M per year", height=420, showlegend=False,
    )
    return fig


DEFAULT_BANDS = [
    {"Band": "Off-peak", "Price ($/MWh)": 45.0, "Hours/year": 4000.0},
    {"Band": "Shoulder", "Price ($/MWh)": 85.0, "Hours/year": 3500.0},
    {"Band": "Peak", "Price ($/MWh)": 220.0, "Hours/year": 1160.0},
    {"Band": "Scarcity", "Price ($/MWh)": 260.0, "Hours/year": 100.0},
]


def _price_bands(edited) -> list:
    """The edited price-duration table as the model wants it.

    Clearing a cell in the `st.data_editor` turns it into NaN. NaN must never
    reach the model -- it propagates through revenue and cash flow until
    `achieved_return`'s guards, which all compare against NaN and are False,
    let bisection run and `capital_recovery_factor` divide by zero. So any
    non-finite cell is read as 0.0 here instead.
    """
    bands = []
    for row in edited.to_dict("records"):
        price = float(row["Price ($/MWh)"])
        hours = float(row["Hours/year"])
        bands.append({
            "price": price if math.isfinite(price) else 0.0,
            "hours": hours if math.isfinite(hours) else 0.0,
        })
    return bands


def _blank_band_cells(edited) -> list:
    """Which (band, column) cells are non-finite and will be read as zero."""
    blanks = []
    for row in edited.to_dict("records"):
        label = row.get("Band", "row")
        for column in ("Price ($/MWh)", "Hours/year"):
            if not math.isfinite(float(row[column])):
                blanks.append(f"{label} — {column}")
    return blanks


def render() -> None:
    # Initialize session state for all tools
    if 'pricing_analysis_data' not in st.session_state:
        st.session_state.pricing_analysis_data = []

    if 'market_power_data' not in st.session_state:
        st.session_state.market_power_data = []

    if 'profit_analysis_data' not in st.session_state:
        st.session_state.profit_analysis_data = []

    if 'supply_bids' not in st.session_state:
        st.session_state.supply_bids = []

    if 'demand_bids' not in st.session_state:
        st.session_state.demand_bids = []

    st.title("Profit & Fixed Cost Recovery")
    st.markdown("**Chapter 2.11: Investment analysis and scarcity rent recovery**")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Investment Parameters")

        st.markdown("**Plant**")
        capacity = st.slider("Capacity (MW)", 100, 2000, 400, 50, key="profit_capacity")
        life_years = st.slider("Technical life (years)", 10, 40, 25, 5,
                               key="profit_life")

        st.markdown("**Capital**")
        capex_per_kw = st.number_input(
            "Overnight capital cost ($/kW)", 100, 6000, 1400, 50,
            key="profit_capex",
            help=(
                f"What it costs to build, per kW, before financing — quoted at "
                f"the reference size of {REFERENCE_CAPACITY_MW:,.0f} MW. The "
                "scale exponent below adjusts it for other sizes."
            ),
        )
        scale_exponent = st.slider(
            "CAPEX scale exponent", 0.60, 1.00, 0.85, 0.05,
            key="profit_scale",
            help=(
                "Bigger plants cost less per kW: total cost rises as size^e. "
                "At 1.00 there are no scale economies and $/kW is flat, which "
                "makes the return on capital identical at every size."
            ),
        )
        wacc = st.slider("WACC — required return (%)", 3.0, 15.0, 7.0, 0.5,
                         key="profit_wacc") / 100

        st.markdown("**Operating cost**")
        fom_per_kw = st.number_input("Fixed O&M ($/kW/year)", 0, 200, 25, 5,
                                     key="profit_fom",
                                     help="Staff, insurance, overhauls — paid whether or not the plant runs.")
        fuel_price = st.number_input("Fuel price ($/GJ)", 0.0, 40.0, 9.5, 0.5,
                                     key="profit_fuel")
        efficiency_pct = st.slider("Thermal efficiency (%)", 20.0, 62.0, 33.0, 1.0,
                                   key="profit_eff",
                                   help="Higher efficiency means less fuel per MWh.")
        vom = st.number_input("Variable O&M ($/MWh)", 0.0, 30.0, 4.0, 0.5,
                              key="profit_vom")

        st.markdown("**Availability**")
        forced_outage_rate = st.slider("Forced outage rate (%)", 0.0, 30.0, 8.0, 1.0,
                                       key="profit_for",
                                       help="Unplanned breakdowns. Random, so they cost hours in every price band.") / 100
        planned_days = st.slider("Planned maintenance (days/year)", 0, 90, 0, 7,
                                 key="profit_planned",
                                 help="Scheduled, so it is taken in the cheapest hours first.")

        st.markdown("**Market prices**")
        st.caption(
            "The price-duration curve: how many hours a year sit at each price. "
            "The plant runs only where the price beats its marginal cost."
        )
        edited = st.data_editor(
            pd.DataFrame(DEFAULT_BANDS), key="profit_bands",
            num_rows="fixed", use_container_width=True,
        )
        blanks = _blank_band_cells(edited)
        if blanks:
            st.warning(
                "Blank cells are being read as zero: " + "; ".join(blanks) + "."
            )
        bands = _price_bands(edited)

        total_band_hours = sum(band["hours"] for band in bands)
        if abs(total_band_hours - 8760) > 1:
            st.warning(
                f"The bands cover {total_band_hours:,.0f} hours; a year is 8,760. "
                "Results are still shown, but the capacity factor will not mean much."
            )

        absorption_mw = st.number_input(
            "Market absorption limit (MW)", 100, 3000, 1150, 50,
            key="profit_absorption",
            help=(
                "The most this plant can actually sell in any hour — the room "
                "the market has for it. Capacity beyond this is built and "
                "maintained but never sells, so it drags the return down."
            ),
        )

        metrics = investment_metrics(
            capacity_mw=capacity, life_years=life_years,
            capex_per_kw=capex_per_kw, wacc=wacc, fom_per_kw=fom_per_kw,
            fuel_price=fuel_price, efficiency_pct=efficiency_pct, vom=vom,
            forced_outage_rate=forced_outage_rate, planned_days=planned_days,
            bands=bands, scale_exponent=scale_exponent,
            absorption_mw=float(absorption_mw),
        )

        st.markdown("**Where the numbers come from**")
        fixed = metrics["fixed"]
        scale_rows = []
        if abs(metrics["capex_per_kw"] - capex_per_kw) > 0.5:
            scale_rows.append({
                "Component": "Scale adjustment",
                "Working": (f"{capex_per_kw:,.0f} $/kW × ({capacity:,.0f}/"
                            f"{REFERENCE_CAPACITY_MW:,.0f})^({scale_exponent:.2f}−1)"),
                "Result": f"${metrics['capex_per_kw']:,.0f}/kW",
            })
        if metrics["idle_mw"] > 0:
            scale_rows.append({
                "Component": "Unsellable capacity",
                "Working": (f"{capacity:,.0f} MW built − {metrics['sold_mw']:,.0f} MW "
                            "the market can take"),
                "Result": f"{metrics['idle_mw']:,.0f} MW idle in every hour",
            })

        # Maintenance usually costs nothing, which makes the slider look broken
        # until you can see WHY: it is taken from hours the plant would not have
        # run in. Showing the revenue forgone turns a dead control into the
        # lesson it was meant to be.
        if planned_days > 0:
            no_outage = investment_metrics(
                capacity_mw=capacity, life_years=life_years,
                capex_per_kw=capex_per_kw, wacc=wacc, fom_per_kw=fom_per_kw,
                fuel_price=fuel_price, efficiency_pct=efficiency_pct, vom=vom,
                forced_outage_rate=forced_outage_rate, planned_days=0.0,
                bands=bands, scale_exponent=scale_exponent,
                absorption_mw=float(absorption_mw),
            )
            forgone = no_outage["short_run_profit"] - metrics["short_run_profit"]
            idle_hours = sum(
                band["available_hours"] for band in metrics["dispatched"]
                if band["running_hours"] == 0
            )
            scale_rows.append({
                "Component": "Planned maintenance",
                "Working": (
                    f"{planned_days:,.0f} days = {planned_days*24:,.0f} h, taken from "
                    f"the cheapest hours first ({idle_hours:,.0f} h a year are below "
                    "marginal cost anyway)"
                ),
                "Result": (
                    "costs no revenue at all" if forgone <= 0 else
                    f"−${forgone/1e6:,.1f}M of short-run profit"
                ),
            })

        st.dataframe(pd.DataFrame(scale_rows + [
            {"Component": "Overnight CAPEX",
             "Working": f"{metrics['capex_per_kw']:,.0f} $/kW × {capacity:,.0f} MW",
             "Result": f"${fixed['capex_total']/1e6:,.1f}M"},
            {"Component": "Capital recovery factor",
             "Working": f"{wacc*100:.1f}% over {life_years} years",
             "Result": f"{fixed['crf']:.4f}"},
            {"Component": "Annualised CAPEX",
             "Working": f"${fixed['capex_total']/1e6:,.1f}M × {fixed['crf']:.4f}",
             "Result": f"${fixed['annualised_capex']/1e6:,.1f}M/yr"},
            {"Component": "Fixed O&M",
             "Working": f"{fom_per_kw:,.0f} $/kW/yr × {capacity:,.0f} MW",
             "Result": f"${fixed['fixed_om']/1e6:,.1f}M/yr"},
            {"Component": "Annual fixed cost",
             "Working": "annualised CAPEX + fixed O&M",
             "Result": f"${fixed['total']/1e6:,.1f}M/yr"},
            {"Component": "Fuel cost",
             "Working": (f"{fuel_price:,.2f} $/GJ × {GJ_PER_MWH:.1f} GJ/MWh ÷ "
                         f"{efficiency_pct:.0f}% efficiency"),
             "Result": f"${fuel_price * GJ_PER_MWH / (efficiency_pct/100):,.1f}/MWh"},
            {"Component": "Marginal cost",
             "Working": f"fuel + {vom:,.1f} $/MWh variable O&M",
             "Result": f"${metrics['marginal_cost']:,.1f}/MWh"},
        ]), use_container_width=True, hide_index=True)

        # Create plots
        st.plotly_chart(create_price_duration_plot(metrics),
                        use_container_width=True, key="profit_duration_plot")
        st.plotly_chart(create_waterfall_plot(metrics),
                        use_container_width=True, key="profit_waterfall_plot")

        # Analysis
        if st.button("Analyze Investment", type="primary", key="profit_add"):
            st.session_state.profit_analysis_data.append({
                "capacity": capacity,
                "marginal_cost": metrics["marginal_cost"],
                "capex_per_kw": capex_per_kw,
                "annual_fixed": metrics["fixed"]["total"],
                "capacity_factor": metrics["capacity_factor"],
                "running_hours": metrics["running_hours"],
                "revenue": metrics["revenue"],
                "variable_cost": metrics["variable_cost"],
                "short_run_profit": metrics["short_run_profit"],
                "long_run_profit": metrics["long_run_profit"],
                "required_return": metrics["required_return"],
                "achieved_return": metrics["achieved_return"],
                "is_viable": metrics["is_viable"],
            })
            st.rerun()

    with col2:
        st.subheader("Investment Analysis")

        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="profit_clear_table"):
                st.session_state.profit_analysis_data = []
                st.rerun()
        with col_clear2:
            if st.button("Clear Analysis", type="secondary", key="profit_clear_analysis"):
                st.session_state.profit_analysis_data = []
                st.rerun()

        # Current scenario metrics
        st.subheader("Current Scenario")
        st.metric("Investment Viability",
                  "✅ VIABLE" if metrics["is_viable"] else "❌ NOT VIABLE")
        st.metric("Marginal cost", f"${metrics['marginal_cost']:,.1f}/MWh")
        st.metric("Annual fixed cost", f"${metrics['fixed']['total']/1e6:,.1f}M")
        st.metric("Capacity factor (derived)", f"{metrics['capacity_factor']:.1f}%",
                  help="An outcome, not a setting: the hours this plant is both available and in merit.")
        st.metric("Short-run profit", f"${metrics['short_run_profit']/1e6:,.1f}M",
                  help="Revenue less variable cost — the scarcity rent available to cover fixed costs.")
        st.metric("Long-run profit", f"${metrics['long_run_profit']/1e6:,.1f}M")
        achieved = metrics["achieved_return"]
        st.metric(
            "Return on capital",
            "never repays" if achieved is None else f"{achieved*100:.1f}%",
            help=f"Against {metrics['required_return']*100:.1f}% required.",
        )

        # Results summary table
        if st.session_state.profit_analysis_data:
            st.subheader("Analysis Results Summary")

            # Create comprehensive results table
            table_data = []
            for i, point in enumerate(st.session_state.profit_analysis_data):
                table_data.append({
                    "Scenario": i + 1,
                    "MW": point["capacity"],
                    "CAPEX ($/kW)": f"{point['capex_per_kw']:,.0f}",
                    "MC ($/MWh)": f"{point['marginal_cost']:,.1f}",
                    "Fixed ($M/yr)": f"{point['annual_fixed']/1e6:,.1f}",
                    "Run hours": f"{point['running_hours']:,.0f}",
                    "CF (%)": f"{point['capacity_factor']:.1f}",
                    "Revenue ($M)": f"{point['revenue']/1e6:,.1f}",
                    "SR profit ($M)": f"{point['short_run_profit']/1e6:,.1f}",
                    "LR profit ($M)": f"{point['long_run_profit']/1e6:,.1f}",
                    "Required (%)": f"{point['required_return']*100:.1f}",
                    "Achieved (%)": ("—" if point["achieved_return"] is None
                                     else f"{point['achieved_return']*100:.1f}"),
                    "Viable": "✅" if point["is_viable"] else "❌",
                })

            results_df = pd.DataFrame(table_data)
            st.dataframe(results_df, use_container_width=True)

            # Investment insights
            st.subheader("Investment Insights")
            if st.session_state.profit_analysis_data:
                latest = st.session_state.profit_analysis_data[-1]

                if latest["running_hours"] == 0:
                    st.error(
                        "🚫 This plant never runs: no price band beats its marginal "
                        f"cost of ${latest['marginal_cost']:,.0f}/MWh. It loses its "
                        f"whole fixed cost of ${latest['annual_fixed']/1e6:,.1f}M."
                    )
                elif latest["capacity_factor"] < 20:
                    st.info(
                        f"🔥 A peaking profile: {latest['capacity_factor']:.1f}% "
                        f"capacity factor over {latest['running_hours']:,.0f} hours. "
                        "Most of the profit comes from the dearest band — set its "
                        "hours to zero and watch how much of it goes."
                    )
                elif latest["capacity_factor"] > 70:
                    st.success(
                        f"🌱 A baseload profile: running {latest['capacity_factor']:.1f}% "
                        "of the year on low marginal cost."
                    )

                if latest["achieved_return"] is None:
                    st.error("📉 The capital is never repaid at any discount rate.")
                elif latest["achieved_return"] < latest["required_return"]:
                    gap = (latest["required_return"] - latest["achieved_return"]) * 100
                    st.error(f"📉 Returns {gap:.1f} points below the {latest['required_return']*100:.1f}% required.")
                else:
                    gap = (latest["achieved_return"] - latest["required_return"]) * 100
                    st.success(f"📈 Returns {gap:.1f} points above the {latest['required_return']*100:.1f}% required.")
        else:
            st.info("Run investment analysis to see comprehensive results table")

    with st.expander("📚 Educational Content"):
        st.markdown("""
        ### Profit and Fixed Cost Recovery (Chapter 2.11)
        """)

        st.markdown("""
        **What the plant costs**

        - **CAPEX** is the overnight capital cost — what it costs to build,
          quoted per kW so plants of different sizes compare. It is paid once,
          so to set it against a year of revenue it is spread over the plant's
          life by the **capital recovery factor**, which also earns the
          investor's required return on the capital still outstanding.
        - **Fixed O&M** is staff, insurance and scheduled overhauls: paid every
          year whether the plant generates or not.
        - **Variable cost** is fuel divided by efficiency, plus variable O&M.
          This is the plant's **marginal cost**, and it decides when it runs.

        **What the plant earns**

        The price-duration curve says how many hours a year sit at each price.
        The plant runs only where price exceeds its marginal cost, and only
        when it is mechanically available. So capacity factor is an *outcome*
        of the market and the machine, never a number an investor chooses.

        **Why scarcity hours decide everything**

        In every hour it runs, the plant earns price minus marginal cost. That
        margin is **scarcity rent**, and it is the only thing available to pay
        back CAPEX and fixed O&M. With the defaults the 100 scarcity hours are
        barely 1% of the year, yet without them **no plant size is viable at
        all**: a 1,000 MW plant goes from +$4.2M to −$9.8M. A hundred hours a
        year at $260/MWh decide whether the thing gets built.

        **Why outage scheduling is an economic decision**

        Forced outages are random, so they cost hours in every band, scarcity
        hours included. Planned maintenance is scheduled, so an operator takes
        it in the cheapest hours — where the plant would not have run anyway.

        With these defaults that makes the maintenance slider look inert, and it
        genuinely is: **6,900 hours a year sit below this plant's marginal
        cost**, so the slider's 90-day maximum (2,160 hours) never reaches an
        hour the plant would have run in. Maintenance here is free. The build-up
        table says so explicitly, and the revenue it costs only becomes non-zero
        past about 288 days. Now move the forced outage rate instead: the same
        lost hours cost real money, because randomness cannot pick its moment.

        **Why plant size has an optimum**

        Two effects pull against each other. Building bigger spreads the fixed
        parts of a project — the connection, the control room, the civil works —
        over more kW, so **CAPEX per kW falls**; that is the scale exponent, and
        with it the return on capital rises with size. But a market only has so
        much room: past the **absorption limit** the extra megawatts are built
        and maintained yet never sell anything, so they add capital without
        adding revenue and the return falls again.

        With the exponent at 1.00 and the absorption limit above your capacity,
        neither effect operates and the return on capital is *identical at every
        plant size* — every term in the calculation is proportional to capacity,
        so it cancels out. Worth seeing once: it is the clearest way to
        understand what the two effects actually add.

        **The defaults: a plant only worth building at one size**

        The page opens on a 400 MW plant that is **not viable** — deliberately.
        Change nothing but the capacity slider:

        | Capacity | Return on capital | |
        |---|---|---|
        | 400 MW | 5.9% | too small — capital too dear per kW |
        | 750 MW | 7.0% | still short of the 7% required |
        | 800 MW | 7.1% | viable |
        | 1,150 MW | 7.7% | best — exactly at the market's limit |
        | 1,200 MW | 7.2% | viable, but past the limit and falling |
        | 1,250 MW | 6.7% | too large — capacity nobody can buy |

        Viable only between roughly 800 and 1,200 MW. Below that the fixed parts
        of the project are spread over too few kW; above it you have built
        something the market cannot absorb, and every idle megawatt still has to
        be paid for. Neither end exists in a model where cost per kW is flat and
        the market is bottomless — which is why sweeping capacity used to change
        the return on capital not at all.

        Note what the scarcity band is doing here: delete its 100 hours and
        **no plant size is viable**, at any size on the slider. A hundred hours
        a year is the difference between an investable project and none.
        """)

        st.markdown("""
        **Long-run vs Short-run Profit**:
        - **Long-run Profit**: Revenue minus cost, where cost includes normal rate of return on investment
        - **Short-run Profit**: Revenue minus variable costs (also called "scarcity rent")
        - **Fixed Cost Recovery**: Must occur through short-run profits over time

        **Investment Economics**:
        - New generation investment requires positive long-run profits
        - Risk premium included in required rate of return
        - Market tightening cycle ensures adequate returns

        **Market Dynamics**:
        1. **Low Prices** → Insufficient cost recovery → No new investment
        2. **Plant Retirements** → Reduced supply capacity
        3. **Market Tightening** → Higher scarcity events and prices
        4. **Price Recovery** → Investment incentives restored

        **Australian NEM Context**:
        - Since 2012: 10 coal plants retired (5,000+ MW capacity)
        - Demonstrates real-world application of these principles
        - Shows importance of scarcity pricing for system adequacy

        ### Key Learning Points:
        - Scarcity rent is essential for viable electricity markets
        - Fixed costs must be recovered through energy market profits
        - Regulatory intervention needed when market power distorts signals
        """)

    # Footer matching original style
    st.markdown("---")
    st.markdown("""
    ### 🎓 Course Integration

    This dashboard integrates core concepts from **ELEC ENG 4087-7087** lectures:

    **Chapter 2.7**: Pool market pricing schemes and their economic implications  
    **Chapter 2.11**: Investment economics and fixed cost recovery through scarcity rent  
    **Chapter 2.12**: Market power analysis using game theory models  

    **Learning Objectives Achieved**:
    - ✅ Understand suppliers' profit and fixed cost recovery mechanisms
    - ✅ Comprehend market power concepts and measurement
    - ✅ Learn market equilibrium analysis in imperfect competition using Bertrand and Cournot models

    **Real-World Context**: Examples from Australian NEM, California ISO, and international electricity markets demonstrate practical application of theoretical concepts.
    """)
