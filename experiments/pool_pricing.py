"""Pool Pricing.

Extracted from week3_pricing_market_power.py (pool_market_pricing_section) on 2026-08-12."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Define the generator data dictionary with correct indentation
COURSE_GENERATORS = {
    'Solar Farm': {'capacity': 200, 'mc': 0, 'color': '#FFD700', 'type': 'Renewable'},
    'Wind Farm': {'capacity': 180, 'mc': 0, 'color': '#87CEEB', 'type': 'Renewable'},
    'Hydro': {'capacity': 150, 'mc': 5, 'color': '#4169E1', 'type': 'Renewable'},
    'Pumped Hydro (Gen)': {'capacity': 120, 'mc': 8, 'color': '#20B2AA', 'type': 'Storage'},
    'Battery Storage': {'capacity': 100, 'mc': 10, 'color': '#9370DB', 'type': 'Storage'},
    'Nuclear': {'capacity': 200, 'mc': 15, 'color': '#32CD32', 'type': 'Baseload'},
    'Coal Black': {'capacity': 180, 'mc': 35, 'color': '#2F4F4F', 'type': 'Fossil'},
    'Coal Brown': {'capacity': 170, 'mc': 42, 'color': '#8B4513', 'type': 'Fossil'},
    'Gas CCGT': {'capacity': 200, 'mc': 65, 'color': '#FF6347', 'type': 'Fossil'},
    'Gas OCGT': {'capacity': 150, 'mc': 95, 'color': '#FF4500', 'type': 'Fossil'},
    'Gas Peaker': {'capacity': 100, 'mc': 125, 'color': '#FF1493', 'type': 'Fossil'},
    'Diesel': {'capacity': 50, 'mc': 180, 'color': '#8B0000', 'type': 'Emergency'}
}

def calculate_market_clearing(generators, demand, pricing_scheme):
    """Calculate market clearing under different pricing schemes"""
    # Sort by marginal cost (merit order)
    sorted_gens = sorted(generators.items(), key=lambda x: x[1]['mc'])
    
    cumulative_capacity = 0
    dispatch_order = []
    clearing_price = 0
    total_dispatched = 0
    
    for name, data in sorted_gens:
        if cumulative_capacity >= demand:
            dispatch_order.append({
                'name': name,
                'capacity': data['capacity'],
                'mc': data['mc'],
                'dispatched': 0,
                'cumulative_start': cumulative_capacity,
                'cumulative_end': cumulative_capacity + data['capacity'],
                'color': data['color']
            })
        else:
            remaining_demand = demand - cumulative_capacity
            dispatched = min(data['capacity'], remaining_demand)
            
            dispatch_order.append({
                'name': name,
                'capacity': data['capacity'],
                'mc': data['mc'],
                'dispatched': dispatched,
                'cumulative_start': cumulative_capacity,
                'cumulative_end': cumulative_capacity + data['capacity'],
                'color': data['color']
            })
            
            total_dispatched += dispatched
            cumulative_capacity += data['capacity']
            
            if dispatched > 0:
                clearing_price = data['mc']
    
    # Calculate costs and revenues
    uniform_total_cost = 0
    payasbid_total_cost = 0
    
    for gen in dispatch_order:
        if gen['dispatched'] > 0:
            uniform_revenue = gen['dispatched'] * clearing_price
            payasbid_revenue = gen['dispatched'] * gen['mc']
            
            uniform_total_cost += uniform_revenue
            payasbid_total_cost += payasbid_revenue
    
    return dispatch_order, clearing_price, total_dispatched, uniform_total_cost, payasbid_total_cost

def create_pricing_comparison_plot(generators, demand, analysis_points):
    """Create pricing scheme comparison plot matching original style"""
    dispatch_order, clearing_price, total_dispatch, uniform_cost, payasbid_cost = calculate_market_clearing(
        generators, demand, 'uniform'
    )
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Uniform Pricing", "Pay-as-Bid Pricing"),
        shared_yaxes=True,
        horizontal_spacing=0.1
    )
    
    # Build supply curve
    cumulative = 0
    for gen in dispatch_order:
        x_vals = [gen['cumulative_start'], gen['cumulative_end']]
        y_vals = [gen['mc'], gen['mc']]
        
        is_dispatched = gen['dispatched'] > 0
        opacity = 1.0 if is_dispatched else 0.3
        line_width = 6 if is_dispatched else 3
        
        # Add to both subplots
        for col in [1, 2]:
            fig.add_trace(
                go.Scatter(
                    x=x_vals, y=y_vals,
                    mode='lines',
                    line=dict(color=gen['color'], width=line_width),
                    opacity=opacity,
                    name=f"{gen['name']}",
                    showlegend=(col == 1),
                    hovertemplate=f"<b>{gen['name']}</b><br>" +
                                 f"Marginal Cost: ${gen['mc']}/MWh<br>" +
                                 f"Dispatched: {gen['dispatched']} MW<extra></extra>"
                ),
                row=1, col=col
            )
    
    # Add demand line and clearing price
    for col in [1, 2]:
        fig.add_vline(x=demand, line_dash="dash", line_color="red", 
                     annotation_text=f"Demand: {demand} MW", row=1, col=col)
    
    # Uniform pricing - clearing price line
    fig.add_hline(y=clearing_price, line_color="green", line_width=3,
                 annotation_text=f"Clearing Price: ${clearing_price}/MWh", row=1, col=1)
    
    # Pay-as-bid annotation
    fig.add_annotation(
        x=demand/2, y=clearing_price + 20,
        text="Each generator paid<br>their bid price",
        showarrow=True,
        arrowhead=2,
        arrowcolor="blue",
        row=1, col=2
    )
    
    # Add analysis points
    colors = ['purple', 'green', 'orange', 'brown', 'pink']
    for i, point in enumerate(analysis_points):
        color = colors[i % len(colors)]
        for col in [1, 2]:
            fig.add_trace(
                go.Scatter(
                    x=[point['demand']],
                    y=[point['clearing_price']],
                    mode='markers',
                    name=f'Analysis Point {i+1}',
                    marker=dict(color=color, size=12, symbol='circle'),
                    showlegend=(col == 1),
                    hovertemplate=(
                        f'<b>Analysis Point {i+1}</b><br>' +
                        f'Demand: {point["demand"]:.0f} MW<br>' +
                        f'Clearing Price: ${point["clearing_price"]:.1f}/MWh<br>' +
                        f'Uniform Cost: ${point["uniform_cost"]:,.0f}<br>' +
                        f'Pay-as-Bid Cost: ${point["payasbid_cost"]:,.0f}<br>' +
                        f'Savings: ${point["savings"]:,.0f}<extra></extra>'
                    )
                ),
                row=1, col=col
            )
    
    fig.update_layout(
        height=500,
        title_text=f"Pool Market Pricing Schemes Comparison",
        title_x=0.5
    )
    
    fig.update_xaxes(title_text="Cumulative Capacity (MW)")
    fig.update_yaxes(title_text="Price ($/MWh)", col=1)
    
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

    st.title("Pool Market Pricing Analysis")
    st.markdown("**Chapter 2.7: Compare uniform pricing and pay-as-bid schemes with realistic generator data**")

    # Create two columns - matching original layout
    col1, col2 = st.columns([2, 1])

    with col1:
        # Demand controller
        demand = st.slider(
            "Electricity Demand (MW)",
            min_value=200,
            max_value=800,
            value=400,
            step=50,
            help="Total electricity demand that must be met"
        )

        # Show generator fleet info with enhanced display
        st.subheader("🏭 Generation Fleet Portfolio")

        # Group generators by type for better organization
        generator_types = {}
        for name, data in COURSE_GENERATORS.items():
            gen_type = data['type']
            if gen_type not in generator_types:
                generator_types[gen_type] = []
            generator_types[gen_type].append((name, data))

        # Display generators grouped by type
        type_colors = {
            'Renewable': '🌱',
            'Storage': '🔋', 
            'Baseload': '⚡',
            'Fossil': '🏭',
            'Emergency': '🚨'
        }

        for gen_type, generators in generator_types.items():
            st.markdown(f"**{type_colors.get(gen_type, '⚡')} {gen_type}**")
            for name, data in generators:
                mc_text = f"${data['mc']}/MWh" if data['mc'] > 0 else "Free"
                st.markdown(f"• **{name}**: {data['capacity']} MW @ {mc_text}")

        # Add scenario controls for renewables
        st.subheader("🌤️ Renewable Generation Scenario")
        renewable_factor = st.slider(
            "Renewable Availability (%)",
            min_value=0,
            max_value=100,
            value=80,
            step=10,
            help="Adjust solar and wind availability based on weather conditions"
        )

        # Adjust renewable capacities based on scenario
        adjusted_generators = COURSE_GENERATORS.copy()
        for name, data in adjusted_generators.items():
            if data['type'] == 'Renewable' and name in ['Solar Farm', 'Wind Farm']:
                adjusted_generators[name] = data.copy()
                adjusted_generators[name]['capacity'] = int(data['capacity'] * renewable_factor / 100)

        # Create and display the plot with adjusted generators
        fig = create_pricing_comparison_plot(adjusted_generators, demand, st.session_state.pricing_analysis_data)
        st.plotly_chart(fig, use_container_width=True, key="pricing_plot")

        # Show current merit order dispatch
        dispatch_order, clearing_price, total_dispatch, uniform_cost, payasbid_cost = calculate_market_clearing(
            adjusted_generators, demand, 'uniform'
        )

        st.subheader("📊 Current Merit Order Dispatch")
        merit_order_data = []
        cumulative_dispatch = 0

        for gen in dispatch_order:
            if gen['dispatched'] > 0:
                cumulative_dispatch += gen['dispatched']
                merit_order_data.append({
                    'Generator': gen['name'],
                    'Type': adjusted_generators[gen['name']]['type'],
                    'MC ($/MWh)': gen['mc'],
                    'Dispatched (MW)': gen['dispatched'],
                    'Cumulative (MW)': cumulative_dispatch,
                    'Status': '✅ Dispatched'
                })
            else:
                merit_order_data.append({
                    'Generator': gen['name'],
                    'Type': adjusted_generators[gen['name']]['type'], 
                    'MC ($/MWh)': gen['mc'],
                    'Dispatched (MW)': 0,
                    'Cumulative (MW)': cumulative_dispatch,
                    'Status': '❌ Not Needed'
                })

        merit_df = pd.DataFrame(merit_order_data)
        st.dataframe(merit_df, use_container_width=True)

        # Current market summary
        st.subheader("💡 Current Market Summary")
        col_sum1, col_sum2, col_sum3 = st.columns(3)

        with col_sum1:
            renewable_dispatch = sum(gen['dispatched'] for gen in dispatch_order 
                                   if adjusted_generators[gen['name']]['type'] == 'Renewable')
            renewable_pct = (renewable_dispatch / total_dispatch * 100) if total_dispatch > 0 else 0
            st.metric("Renewable Share", f"{renewable_pct:.1f}%", f"{renewable_dispatch:.0f} MW")

        with col_sum2:
            storage_dispatch = sum(gen['dispatched'] for gen in dispatch_order 
                                 if adjusted_generators[gen['name']]['type'] == 'Storage')
            st.metric("Storage Dispatch", f"{storage_dispatch:.0f} MW")

        with col_sum3:
            fossil_dispatch = sum(gen['dispatched'] for gen in dispatch_order 
                                if adjusted_generators[gen['name']]['type'] == 'Fossil')
            st.metric("Fossil Dispatch", f"{fossil_dispatch:.0f} MW")

        # Manual analysis point addition
        st.subheader("Add Analysis Point")
        if st.button("Analyze Current Scenario", type="primary", key="pricing_add"):
            dispatch_order, clearing_price, total_dispatch, uniform_cost, payasbid_cost = calculate_market_clearing(
                adjusted_generators, demand, 'uniform'
            )

            savings = uniform_cost - payasbid_cost

            # Calculate additional metrics for renewables analysis
            renewable_dispatch = sum(gen['dispatched'] for gen in dispatch_order 
                                   if adjusted_generators[gen['name']]['type'] == 'Renewable')
            renewable_pct = (renewable_dispatch / total_dispatch * 100) if total_dispatch > 0 else 0

            storage_dispatch = sum(gen['dispatched'] for gen in dispatch_order 
                                 if adjusted_generators[gen['name']]['type'] == 'Storage')

            st.session_state.pricing_analysis_data.append({
                'demand': demand,
                'renewable_factor': renewable_factor,
                'clearing_price': clearing_price,
                'total_dispatch': total_dispatch,
                'uniform_cost': uniform_cost,
                'payasbid_cost': payasbid_cost,
                'savings': savings,
                'renewable_dispatch': renewable_dispatch,
                'renewable_pct': renewable_pct,
                'storage_dispatch': storage_dispatch
            })
            st.rerun()

    with col2:
        st.subheader("Analysis Results")

        # Clear buttons - matching original style
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="pricing_clear_table"):
                st.session_state.pricing_analysis_data = []
                st.rerun()
        with col_clear2:
            if st.button("Clear Graph", type="secondary", key="pricing_clear_graph"):
                st.session_state.pricing_analysis_data = []
                st.rerun()

        # Display results table - enhanced with renewable metrics
        if st.session_state.pricing_analysis_data:
            df_data = []
            for i, point in enumerate(st.session_state.pricing_analysis_data):
                df_data.append({
                    'Point': i + 1,
                    'Demand (MW)': f"{point['demand']:.0f}",
                    'Renewable (%)': f"{point.get('renewable_factor', 'N/A')}%",
                    'Price ($/MWh)': f"{point['clearing_price']:.1f}",
                    'Renewable Share': f"{point.get('renewable_pct', 0):.1f}%",
                    'Uniform Cost ($)': f"{point['uniform_cost']:,.0f}",
                    'Pay-as-Bid ($)': f"{point['payasbid_cost']:,.0f}",
                    'Savings ($)': f"{point['savings']:,.0f}"
                })

            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)

            # Latest point details - enhanced with renewable analysis
            if st.session_state.pricing_analysis_data:
                last_point = st.session_state.pricing_analysis_data[-1]
                st.subheader("Latest Analysis")

                st.metric("Clearing Price", f"${last_point['clearing_price']:.1f}/MWh",
                         help="Set by marginal (most expensive dispatched) generator")

                st.metric("Renewable Generation", 
                         f"{last_point.get('renewable_dispatch', 0):.0f} MW",
                         f"{last_point.get('renewable_pct', 0):.1f}% of total dispatch")

                st.metric("Storage Dispatch", f"{last_point.get('storage_dispatch', 0):.0f} MW")

                st.metric("Pay-as-Bid Savings", f"${last_point['savings']:,.0f}",
                         f"vs Uniform Pricing")

                # Market insights based on renewables
                if last_point.get('renewable_pct', 0) > 60:
                    st.success("🌱 High renewable penetration - low marginal costs driving market prices down!")
                elif last_point.get('clearing_price', 0) == 0:
                    st.info("💡 Zero marginal cost setting - renewables are price setters!")
                elif last_point.get('clearing_price', 0) > 100:
                    st.warning("⚡ High prices indicate scarcity - fossil fuels or storage setting price")
        else:
            st.info("Add analysis points to see results with renewable integration")

    with st.expander("📚 Educational Content"):
        st.markdown("""
        ### Pool Market Pricing Schemes (Chapter 2.7)

        **Enhanced Generator Fleet Analysis**:
        This tool now includes a comprehensive generation portfolio reflecting modern electricity markets:

        **🌱 Renewable Generators**:
        - **Solar Farms**: Zero marginal cost, weather-dependent availability
        - **Wind Farms**: Zero marginal cost, variable output
        - **Hydro**: Very low marginal cost, flexible dispatch

        **🔋 Storage Technologies**:
        - **Pumped Hydro Storage**: Low marginal cost when generating
        - **Battery Storage**: Slightly higher cost but fast response

        **⚡ Traditional Generators**:
        - **Nuclear**: Low marginal cost, baseload operation
        - **Coal**: Medium marginal cost, various grades (black/brown)
        - **Gas**: Range from CCGT to peaking units
        - **Diesel**: Emergency/backup, highest marginal cost

        **Key Learning Points with Renewables**:

        **1. Merit Order Impact**:
        - Renewables with zero marginal cost always dispatch first
        - Storage provides flexibility and can set marginal price
        - Fossil fuels increasingly serve as backup/peak generation

        **2. Price Formation Effects**:
        - High renewable penetration → Lower clearing prices
        - Storage can reduce price volatility
        - Peak periods may see significant price spikes when renewables unavailable

        **3. Market Design Implications**:
        - Need for scarcity pricing to ensure adequacy
        - Storage arbitrage opportunities
        - Integration challenges for variable renewable energy

        **4. Real Australian NEM Context**:
        - Growing renewable penetration changing price patterns
        - Negative pricing during high solar/wind periods
        - Storage investments increasing market efficiency

        **Interactive Features**:
        - Adjust renewable availability to simulate weather conditions
        - Observe how renewable penetration affects clearing prices
        - Compare pricing schemes under different generation mixes
        - Analyze storage dispatch patterns and market impact
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
