"""Profit Cost Recovery.

Extracted from week3_pricing_market_power.py (profit_cost_recovery_section) on 2026-08-12."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# --- Economics -------------------------------------------------------------
#
# Pure functions: numbers in, numbers out, no Streamlit. Everything the page
# displays is derived here so a student can trace any figure on screen back to
# an input, and so the model can be tested without rendering anything.

GJ_PER_MWH = 3.6
HOURS_PER_YEAR = 8760


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


def annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw) -> dict:
    """Annualised CAPEX and fixed O&M, each kept separate for display."""
    capacity_kw = capacity_mw * 1000
    capex_total = capex_per_kw * capacity_kw
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
                       planned_days, bands) -> dict:
    """Everything the page displays, from what the student typed."""
    mc = marginal_cost(fuel_price, efficiency_pct, vom)
    fixed = annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw)
    dispatched = dispatch(bands, mc, forced_outage_rate, planned_days)

    running_hours = sum(band["running_hours"] for band in dispatched)
    energy = capacity_mw * running_hours
    revenue = sum(band["price"] * capacity_mw * band["running_hours"]
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
        "capacity_factor": 100 * energy / (capacity_mw * HOURS_PER_YEAR),
        "required_return": wacc,
        "achieved_return": achieved_return(
            fixed["capex_total"], short_run_profit - fixed["fixed_om"], life_years
        ),
        "is_viable": long_run_profit >= 0,
    }


def calculate_investment_metrics(capacity, marginal_cost, fixed_cost_annual, required_ror, capacity_factor_input):
    """Calculate investment viability metrics with user-defined capacity factor"""
    # Use input capacity factor to determine operating hours
    total_hours = int(8760 * capacity_factor_input / 100)
    
    # Market scenarios - simplified to use capacity factor
    # Assume average market price based on marginal cost and scarcity conditions
    if marginal_cost <= 50:
        avg_market_price = 75  # Base load operation
    elif marginal_cost <= 150:
        avg_market_price = 180  # Mid-merit operation
    else:
        avg_market_price = 500  # Peaking operation with high scarcity pricing
    
    # Calculate revenue only when market price > marginal cost
    if avg_market_price > marginal_cost:
        total_revenue = capacity * avg_market_price * total_hours
        total_variable_cost = marginal_cost * capacity * total_hours
    else:
        total_revenue = 0
        total_variable_cost = 0
        total_hours = 0
    
    short_run_profit = total_revenue - total_variable_cost
    total_annual_cost = fixed_cost_annual * (1 + required_ror)  # Include required return
    long_run_profit = short_run_profit - total_annual_cost
    
    # Calculate actual rate of return achieved
    if fixed_cost_annual > 0:
        actual_ror = (short_run_profit - fixed_cost_annual) / fixed_cost_annual
    else:
        actual_ror = 0
    
    is_viable = long_run_profit >= 0
    
    return {
        'total_revenue': total_revenue,
        'total_variable_cost': total_variable_cost,
        'short_run_profit': short_run_profit,
        'long_run_profit': long_run_profit,
        'capacity_factor': capacity_factor_input,  # Use input value
        'actual_ror': actual_ror,
        'required_ror': required_ror,
        'is_viable': is_viable,
        'total_hours': total_hours,
        'avg_market_price': avg_market_price
    }

def create_profit_analysis_plot(analysis_points):
    """Create profit and cost recovery analysis plot"""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Investment Viability Gauge", "Rate of Return Analysis", 
                       "Revenue vs Cost Breakdown", "Capacity Factor Distribution"),
        specs=[[{"type": "indicator"}, {"type": "bar"}],
               [{"type": "bar"}, {"type": "pie"}]]
    )
    
    if analysis_points:
        latest = analysis_points[-1]
        
        # Investment viability gauge
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=latest['long_run_profit']/1_000_000,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Long-run Profit ($M)"},
                delta={'reference': 0},
                gauge={
                    'axis': {'range': [-100, 100]},
                    'bar': {'color': "#4ECDC4" if latest['is_viable'] else "#FF6B6B"},
                    'steps': [
                        {'range': [-100, 0], 'color': "lightcoral"},
                        {'range': [0, 100], 'color': "lightgreen"}
                    ],
                    'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 0}
                }
            ),
            row=1, col=1
        )
        
        # Rate of return comparison
        ror_categories = ['Required RoR', 'Actual RoR']
        ror_values = [latest['required_ror'] * 100, latest['actual_ror'] * 100]
        ror_colors = ['#FF6B6B', '#4ECDC4' if latest['actual_ror'] >= latest['required_ror'] else '#FF6B6B']
        
        fig.add_trace(
            go.Bar(x=ror_categories, y=ror_values, name="Rate of Return",
                   marker_color=ror_colors, showlegend=False,
                   text=[f"{val:.1f}%" for val in ror_values],
                   textposition="outside"),
            row=1, col=2
        )
        
        # Revenue vs Cost breakdown
        financial_categories = ['Revenue', 'Variable Cost', 'Fixed Cost', 'Profit']
        financial_values = [
            latest['total_revenue']/1_000_000,
            latest['total_variable_cost']/1_000_000,
            (latest['total_revenue'] - latest['short_run_profit'])/1_000_000,
            latest['long_run_profit']/1_000_000
        ]
        financial_colors = ['#4ECDC4', '#FF6B6B', '#FFA500', 
                           '#32CD32' if latest['long_run_profit'] > 0 else '#FF4500']
        
        fig.add_trace(
            go.Bar(x=financial_categories, y=financial_values, name="Financial Breakdown",
                   marker_color=financial_colors, showlegend=False,
                   text=[f"${val:.1f}M" for val in financial_values],
                   textposition="outside"),
            row=2, col=1
        )
        
        # Capacity factor distribution
        operating_hours = latest['total_hours']
        idle_hours = 8760 - operating_hours
        fig.add_trace(
            go.Pie(labels=['Operating', 'Idle'], 
                   values=[operating_hours, idle_hours],
                   marker_colors=['#4ECDC4', '#F0F0F0'], 
                   showlegend=False,
                   textinfo='label+percent',
                   hovertemplate='%{label}: %{value} hours<br>%{percent}<extra></extra>'),
            row=2, col=2
        )
    
    fig.update_layout(height=700, title_text="Investment Financial Analysis")
    fig.update_yaxes(title_text="Return (%)", row=1, col=2)
    fig.update_xaxes(title_text="Metric", row=1, col=2)
    fig.update_yaxes(title_text="Amount ($M)", row=2, col=1)
    fig.update_xaxes(title_text="Category", row=2, col=1)
    
    return fig

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

        # Investment inputs - enhanced range and capacity factor input
        capacity = st.slider("Plant Capacity (MW)", 100, 1000, 400, 50)

        marginal_cost = st.number_input(
            "Marginal Cost ($/MWh)", 
            min_value=0,
            max_value=1000,
            value=45,
            step=5,
            help="Can go up to $1000/MWh for emergency peaking units"
        )

        fixed_cost_annual = st.number_input("Annual Fixed Cost ($M)", 10, 500, 80, 10) * 1_000_000

        required_ror = st.slider("Required Rate of Return (%)", 5.0, 15.0, 8.0, 0.5) / 100

        # Capacity factor as input
        capacity_factor_input = st.slider(
            "Expected Capacity Factor (%)",
            min_value=5.0,
            max_value=95.0,
            value=40.0,
            step=5.0,
            help="Percentage of time plant operates annually (input parameter)"
        )

        # Calculate metrics with input capacity factor
        metrics = calculate_investment_metrics(capacity, marginal_cost, fixed_cost_annual, required_ror, capacity_factor_input)

        # Create plot
        fig = create_profit_analysis_plot(st.session_state.profit_analysis_data)
        st.plotly_chart(fig, use_container_width=True, key="profit_plot")

        # Analysis
        if st.button("Analyze Investment", type="primary", key="profit_add"):
            st.session_state.profit_analysis_data.append({
                'capacity': capacity,
                'marginal_cost': marginal_cost,
                'capacity_factor': capacity_factor_input,
                'total_revenue': metrics['total_revenue'],
                'total_variable_cost': metrics['total_variable_cost'],
                'short_run_profit': metrics['short_run_profit'],
                'long_run_profit': metrics['long_run_profit'],
                'required_ror': metrics['required_ror'],
                'actual_ror': metrics['actual_ror'],
                'is_viable': metrics['is_viable'],
                'total_hours': metrics['total_hours'],
                'avg_market_price': metrics['avg_market_price']
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
                 "✅ VIABLE" if metrics['is_viable'] else "❌ NOT VIABLE")
        st.metric("Capacity Factor", f"{metrics['capacity_factor']:.1f}%")
        st.metric("Required Rate of Return", f"{metrics['required_ror']*100:.1f}%")
        st.metric("Actual Rate of Return", f"{metrics['actual_ror']*100:.1f}%")
        st.metric("Long-run Profit", f"${metrics['long_run_profit']/1_000_000:.1f}M")

        # Results summary table
        if st.session_state.profit_analysis_data:
            st.subheader("Analysis Results Summary")

            # Create comprehensive results table
            table_data = []
            for i, point in enumerate(st.session_state.profit_analysis_data):
                table_data.append({
                    'Scenario': i + 1,
                    'Capacity (MW)': point['capacity'],
                    'MC ($/MWh)': point['marginal_cost'],
                    'CF (%)': f"{point['capacity_factor']:.1f}",
                    'Market Price ($/MWh)': f"{point['avg_market_price']:.0f}",
                    'Revenue ($M)': f"{point['total_revenue']/1_000_000:.1f}",
                    'Variable Cost ($M)': f"{point['total_variable_cost']/1_000_000:.1f}",
                    'Short-run Profit ($M)': f"{point['short_run_profit']/1_000_000:.1f}",
                    'Long-run Profit ($M)': f"{point['long_run_profit']/1_000_000:.1f}",
                    'Required RoR (%)': f"{point['required_ror']*100:.1f}",
                    'Actual RoR (%)': f"{point['actual_ror']*100:.1f}",
                    'Viable': "✅" if point['is_viable'] else "❌"
                })

            results_df = pd.DataFrame(table_data)
            st.dataframe(results_df, use_container_width=True)

            # Investment insights
            st.subheader("Investment Insights")
            if st.session_state.profit_analysis_data:
                latest = st.session_state.profit_analysis_data[-1]

                if latest['marginal_cost'] > 500:
                    st.warning("⚡ Very high marginal cost - suitable only for emergency/scarcity pricing scenarios")
                elif latest['marginal_cost'] > 200:
                    st.info("🔥 High marginal cost - peaking plant requiring scarcity rents for viability")
                elif latest['marginal_cost'] < 20:
                    st.success("🌱 Low marginal cost - likely baseload renewable or nuclear technology")

                if latest['actual_ror'] < latest['required_ror']:
                    st.error(f"📉 Investment returns {(latest['actual_ror'] - latest['required_ror'])*100:.1f}% below required rate")
                else:
                    st.success(f"📈 Investment exceeds required return by {(latest['actual_ror'] - latest['required_ror'])*100:.1f}%")
        else:
            st.info("Run investment analysis to see comprehensive results table")

    with st.expander("📚 Educational Content"):
        st.markdown("""
        ### Profit and Fixed Cost Recovery (Chapter 2.11)

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
