"""Interactive Clearing.

Extracted from week3_pricing_market_power.py (interactive_market_clearing_section) on 2026-08-12."""

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

def calculate_generator_metrics(dispatched_offers, clearing_price):
    """Calculate comprehensive metrics for generator dispatch results with aggregated view"""
    # First group by generator
    generator_results = {}
    
    for offer in dispatched_offers:
        gen_name = offer['generator']
        if gen_name not in generator_results:
            generator_results[gen_name] = {
                'total_capacity': 0,
                'total_dispatched': 0,
                'revenue': 0,
                'cost': 0,
                'accepted_tiers': [],
                'color': offer['color'],
                'type': offer['type']
            }
        
        generator_results[gen_name]['total_capacity'] += offer['capacity']
        if offer['dispatched'] > 0:
            generator_results[gen_name]['total_dispatched'] += offer['dispatched']
            generator_results[gen_name]['revenue'] += offer['dispatched'] * clearing_price
            generator_results[gen_name]['cost'] += offer['dispatched'] * offer['price']
            generator_results[gen_name]['accepted_tiers'].append(offer['tier'])
    
    # Convert to list of results
    results = []
    for gen_name, data in generator_results.items():
        if data['total_dispatched'] > 0:  # Only show dispatched generators
            # Format accepted tiers nicely
            accepted_tiers = sorted(data['accepted_tiers'])
            if len(accepted_tiers) == 1:
                tiers_text = f"Tier {accepted_tiers[0]}"
            elif len(accepted_tiers) == 2:
                tiers_text = f"Tiers {accepted_tiers[0]} & {accepted_tiers[1]}"
            else:
                tiers_text = f"Tiers {', '.join(map(str, accepted_tiers[:-1]))} & {accepted_tiers[-1]}"
            
            results.append({
                'Generator': gen_name,
                'Accepted Tiers': tiers_text,
                'Capacity (MW)': f"{data['total_capacity']:.1f}",
                'Dispatched (MW)': f"{data['total_dispatched']:.1f}",
                'Dispatch (%)': f"{(data['total_dispatched']/data['total_capacity']*100):.1f}%",
                'Revenue ($)': f"${data['revenue']:,.0f}",
                'Cost ($)': f"${data['cost']:,.0f}",
                'Profit ($)': f"${data['revenue'] - data['cost']:,.0f}"
            })
    
    # Sort by dispatch amount (descending)
    results.sort(key=lambda x: float(x['Dispatched (MW)'].replace(',', '')), reverse=True)
    return results

def calculate_demand_metrics(satisfied_demands, clearing_price):
    """Calculate comprehensive metrics for retailer demand satisfaction with aggregated view"""
    # First group by retailer
    retailer_results = {}
    
    for demand in satisfied_demands:
        retailer = demand['retailer']
        if retailer not in retailer_results:
            retailer_results[retailer] = {
                'total_demand': 0,
                'total_satisfied': 0,
                'total_expense': 0,
                'total_value': 0,
                'accepted_tiers': []
            }
        
        retailer_results[retailer]['total_demand'] += demand['demand']
        if demand['satisfied'] > 0:
            retailer_results[retailer]['total_satisfied'] += demand['satisfied']
            retailer_results[retailer]['total_expense'] += demand['satisfied'] * clearing_price
            retailer_results[retailer]['total_value'] += demand['satisfied'] * demand['price']
            retailer_results[retailer]['accepted_tiers'].append(demand['tier'])
    
    # Convert to list of results
    results = []
    for retailer, data in retailer_results.items():
        # Format accepted tiers nicely
        accepted_tiers = sorted(data['accepted_tiers'])
        if len(accepted_tiers) == 1:
            tiers_text = f"Tier {accepted_tiers[0]}"
        elif len(accepted_tiers) == 2:
            tiers_text = f"Tiers {accepted_tiers[0]} & {accepted_tiers[1]}"
        else:
            tiers_text = f"Tiers {', '.join(map(str, accepted_tiers[:-1]))} & {accepted_tiers[-1]}"
        
        results.append({
            'Retailer': retailer,
            'Accepted Tiers': tiers_text,
            'Demand (MW)': f"{data['total_demand']:.1f}",
            'Satisfied (MW)': f"{data['total_satisfied']:.1f}",
            'Satisfied (%)': f"{(data['total_satisfied']/data['total_demand']*100):.1f}%",
            'Expense ($)': f"${data['total_expense']:,.0f}",
            'Value ($)': f"${data['total_value']:,.0f}",
            'Surplus ($)': f"${data['total_value'] - data['total_expense']:,.0f}"
        })
    
    return results

def generate_multi_tier_offers():
    """Generate 3-tier supply offers for each generator"""
    offers = []
    for name, gen in COURSE_GENERATORS.items():
        base_capacity = gen['capacity'] / 3  # Split capacity into three tiers
        base_mc = gen['mc']
        
        # Tier 1: Base capacity at marginal cost
        offers.append({
            'generator': name,
            'tier': 1,
            'capacity': base_capacity,
            'price': base_mc,
            'color': gen['color'],
            'type': gen['type']
        })
        
        # Tier 2: Mid capacity at 150% marginal cost
        offers.append({
            'generator': name,
            'tier': 2,
            'capacity': base_capacity,
            'price': base_mc * 1.5 if base_mc > 0 else 10,
            'color': gen['color'],
            'type': gen['type']
        })
        
        # Tier 3: Peak capacity at 200% marginal cost
        offers.append({
            'generator': name,
            'tier': 3,
            'capacity': base_capacity,
            'price': base_mc * 2 if base_mc > 0 else 20,
            'color': gen['color'],
            'type': gen['type']
        })
    
    return sorted(offers, key=lambda x: x['price'])

def generate_multi_tier_demands():
    """Generate 3-tier demand bids for 4 retailers"""
    retailers = [
        {'name': 'Retailer A', 'base_demand': 200, 'max_price': 120},
        {'name': 'Retailer B', 'base_demand': 180, 'max_price': 100},
        {'name': 'Retailer C', 'base_demand': 150, 'max_price': 90},
        {'name': 'Retailer D', 'base_demand': 120, 'max_price': 80}
    ]
    
    demands = []
    for retailer in retailers:
        base_demand = retailer['base_demand'] / 3  # Split demand into three tiers
        max_price = retailer['max_price']
        
        # Tier 1: High priority at max price
        demands.append({
            'retailer': retailer['name'],
            'tier': 1,
            'demand': base_demand,
            'price': max_price
        })
        
        # Tier 2: Medium priority at 80% max price
        demands.append({
            'retailer': retailer['name'],
            'tier': 2,
            'demand': base_demand,
            'price': max_price * 0.8
        })
        
        # Tier 3: Low priority at 60% max price
        demands.append({
            'retailer': retailer['name'],
            'tier': 3,
            'demand': base_demand,
            'price': max_price * 0.6
        })
    
    return sorted(demands, key=lambda x: x['price'], reverse=True)

def find_market_equilibrium_multi_tier(supply_offers, demand_bids, single_demand_mode=False, total_demand=None):
    """Find market equilibrium with multi-tier offers and bids"""
    if single_demand_mode:
        # Simple mode: Just find generators to meet fixed demand
        dispatched_offers = []
        remaining_demand = total_demand
        clearing_price = 0
        
        for offer in supply_offers:
            if remaining_demand <= 0:
                offer['dispatched'] = 0
            else:
                dispatched = min(offer['capacity'], remaining_demand)
                offer['dispatched'] = dispatched
                remaining_demand -= dispatched
                if dispatched > 0:
                    clearing_price = offer['price']
            dispatched_offers.append(offer)
        
        return dispatched_offers, [], clearing_price, total_demand - remaining_demand
    
    else:
        # Complex mode: Find intersection of supply and demand curves
        # Sort by price (ascending for supply, descending for demand)
        supply_sorted = sorted(supply_offers, key=lambda x: x['price'])
        demand_sorted = sorted(demand_bids, key=lambda x: x['price'], reverse=True)
        
        # Find intersection
        supply_qty = 0
        demand_qty = 0
        clearing_price = 0
        equilibrium_qty = 0
        
        for supply in supply_sorted:
            supply_qty += supply['capacity']
            new_demand_qty = 0
            
            for demand in demand_sorted:
                if demand['price'] >= supply['price']:
                    new_demand_qty += demand['demand']
                else:
                    break
            
            if new_demand_qty <= supply_qty:
                clearing_price = supply['price']
                equilibrium_qty = new_demand_qty
                break
            
            demand_qty = new_demand_qty
        
        # Determine dispatch quantities
        dispatched_offers = []
        remaining_qty = equilibrium_qty
        
        for offer in supply_sorted:
            if remaining_qty <= 0:
                offer['dispatched'] = 0
            else:
                dispatched = min(offer['capacity'], remaining_qty)
                offer['dispatched'] = dispatched
                remaining_qty -= dispatched
            dispatched_offers.append(offer)
        
        # Determine satisfied demands
        satisfied_demands = []
        remaining_qty = equilibrium_qty
        
        for demand in demand_sorted:
            if remaining_qty <= 0:
                demand['satisfied'] = 0
            else:
                satisfied = min(demand['demand'], remaining_qty)
                demand['satisfied'] = satisfied
                remaining_qty -= satisfied
            satisfied_demands.append(demand)
        
        return dispatched_offers, satisfied_demands, clearing_price, equilibrium_qty

def create_market_clearing_plot(supply_offers, demand_bids, dispatched_offers, satisfied_demands, clearing_price, equilibrium_qty, single_demand_mode=False):
    """Create market clearing visualization with supply and demand curves and welfare areas"""
    fig = go.Figure()
    
    # Calculate welfare areas for display
    consumer_surplus = 0
    producer_surplus = 0
    total_cost = 0
    
    if not single_demand_mode and demand_bids:
        # Build demand curve points for proper shading
        demand_curve_x = [0]
        demand_curve_y = [float('inf')]  # Start very high
        cumulative_demand = 0
        
        sorted_demands = sorted(demand_bids, key=lambda x: x['price'], reverse=True)
        
        for demand in sorted_demands:
            demand_curve_x.extend([cumulative_demand, cumulative_demand + demand['demand']])
            demand_curve_y.extend([demand['price'], demand['price']])
            cumulative_demand += demand['demand']
        
        # Close the demand curve
        demand_curve_x.append(cumulative_demand)
        demand_curve_y.append(0)
        
        # Add demand curve as a line
        fig.add_trace(go.Scatter(
            x=demand_curve_x[1:-1],  # Remove the infinite start and zero end
            y=demand_curve_y[1:-1],
            mode='lines',
            name='Demand Curve',
            line=dict(color='red', width=3),
            showlegend=True
        ))
        
        # Add individual demand blocks with satisfaction status
        cumulative_demand = 0
        for demand in sorted_demands:
            is_satisfied = demand.get('satisfied', 0) > 0
            opacity = 1.0 if is_satisfied else 0.3
            
            fig.add_trace(go.Scatter(
                x=[cumulative_demand, cumulative_demand + demand['demand']],
                y=[demand['price'], demand['price']],
                name=f"{demand['retailer']} (Tier {demand['tier']})",
                line=dict(color='red', width=4),
                opacity=opacity,
                showlegend=True,
                hovertemplate=(
                    f"<b>{demand['retailer']}</b><br>" +
                    f"Tier: {demand['tier']}<br>" +
                    f"Price: ${demand['price']:.2f}/MWh<br>" +
                    f"Demand: {demand['demand']:.1f} MW<br>" +
                    f"Satisfied: {demand.get('satisfied', 0):.1f} MW<extra></extra>"
                )
            ))
            
            # Calculate consumer surplus for satisfied demand
            if is_satisfied:
                satisfied_qty = demand.get('satisfied', 0)
                consumer_surplus += (demand['price'] - clearing_price) * satisfied_qty
            
            cumulative_demand += demand['demand']
    
    # Build supply curve points for proper shading
    supply_curve_x = [0]
    supply_curve_y = [0]
    cumulative_supply = 0
    
    sorted_offers = sorted(dispatched_offers, key=lambda x: x['price'])
    
    for offer in sorted_offers:
        supply_curve_x.extend([cumulative_supply, cumulative_supply + offer['capacity']])
        supply_curve_y.extend([offer['price'], offer['price']])
        cumulative_supply += offer['capacity']
    
    # Add supply curve as a line
    fig.add_trace(go.Scatter(
        x=supply_curve_x,
        y=supply_curve_y,
        mode='lines',
        name='Supply Curve',
        line=dict(color='blue', width=3),
        showlegend=True
    ))
    
    # Add individual generator blocks with dispatch status
    cumulative_supply = 0
    for offer in sorted_offers:
        is_dispatched = offer['dispatched'] > 0
        opacity = 1.0 if is_dispatched else 0.3
        
        fig.add_trace(go.Scatter(
            x=[cumulative_supply, cumulative_supply + offer['capacity']],
            y=[offer['price'], offer['price']],
            name=f"{offer['generator']} (Tier {offer['tier']})",
            line=dict(color=offer['color'], width=6),
            opacity=opacity,
            showlegend=True,
            hovertemplate=(
                f"<b>{offer['generator']}</b><br>" +
                f"Tier: {offer['tier']}<br>" +
                f"Price: ${offer['price']:.2f}/MWh<br>" +
                f"Capacity: {offer['capacity']:.1f} MW<br>" +
                f"Dispatched: {offer['dispatched']:.1f} MW<extra></extra>"
            )
        ))
        
        # Calculate costs and producer surplus for dispatched offers
        if is_dispatched:
            dispatched_qty = offer['dispatched']
            total_cost += offer['price'] * dispatched_qty
            producer_surplus += (clearing_price - offer['price']) * dispatched_qty
        
        cumulative_supply += offer['capacity']
    
    # Add welfare area shadings
    if equilibrium_qty > 0:
        # 1. Consumer Surplus (area above clearing price, below demand curve)
        if not single_demand_mode and demand_bids:
            # Create consumer surplus shading
            cs_x = [0]
            cs_y = [clearing_price]
            cumulative_demand = 0
            
            for demand in sorted_demands:
                if demand.get('satisfied', 0) > 0:
                    satisfied_qty = demand.get('satisfied', 0)
                    cs_x.extend([cumulative_demand, cumulative_demand + satisfied_qty])
                    cs_y.extend([demand['price'], demand['price']])
                    cumulative_demand += satisfied_qty
                    if cumulative_demand >= equilibrium_qty:
                        break
            
            # Close the area
            cs_x.append(equilibrium_qty)
            cs_y.append(clearing_price)
            
            fig.add_trace(go.Scatter(
                x=cs_x,
                y=cs_y,
                fill='toself',
                fillcolor='rgba(144,238,144,0.4)',  # Light green
                line=dict(width=0),
                name='Consumer Surplus',
                showlegend=True,
                hovertemplate=f'Consumer Surplus: ${consumer_surplus:,.0f}<extra></extra>'
            ))
        
        # 2. Producer Surplus/Scarcity Rent (area above supply curve, below clearing price)
        ps_x = [0]
        ps_y = [clearing_price]
        cumulative_supply = 0
        
        for offer in sorted_offers:
            if offer['dispatched'] > 0:
                dispatched_qty = offer['dispatched']
                ps_x.extend([cumulative_supply, cumulative_supply + dispatched_qty])
                ps_y.extend([offer['price'], offer['price']])
                cumulative_supply += dispatched_qty
                if cumulative_supply >= equilibrium_qty:
                    break
        
        # Close the area
        ps_x.append(equilibrium_qty)
        ps_y.append(clearing_price)
        
        fig.add_trace(go.Scatter(
            x=ps_x,
            y=ps_y,
            fill='toself',
            fillcolor='rgba(173,216,230,0.4)',  # Light blue
            line=dict(width=0),
            name='Producer Surplus (Scarcity Rent)',
            showlegend=True,
            hovertemplate=f'Producer Surplus: ${producer_surplus:,.0f}<extra></extra>'
        ))
        
        # 3. Total Cost (area below supply curve)
        cost_x = [0, 0]
        cost_y = [0, 0]
        cumulative_supply = 0
        
        for offer in sorted_offers:
            if offer['dispatched'] > 0:
                dispatched_qty = offer['dispatched']
                cost_x.extend([cumulative_supply, cumulative_supply + dispatched_qty])
                cost_y.extend([offer['price'], offer['price']])
                cumulative_supply += dispatched_qty
                if cumulative_supply >= equilibrium_qty:
                    break
        
        # Close the area to x-axis
        cost_x.extend([equilibrium_qty, 0])
        cost_y.extend([0, 0])
        
        fig.add_trace(go.Scatter(
            x=cost_x,
            y=cost_y,
            fill='toself',
            fillcolor='rgba(255,182,193,0.4)',  # Light pink
            line=dict(width=0),
            name='Total Generation Cost',
            showlegend=True,
            hovertemplate=f'Total Cost: ${total_cost:,.0f}<extra></extra>'
        ))
    
    # Add clearing price line and vertical line at equilibrium
    fig.add_hline(
        y=clearing_price,
        line_color="green",
        line_width=3,
        line_dash="dash",
        annotation_text=f"Clearing Price: ${clearing_price:.2f}/MWh"
    )
    
    fig.add_vline(
        x=equilibrium_qty,
        line_color="green",
        line_width=3,
        line_dash="dash",
        annotation_text=f"Cleared Quantity: {equilibrium_qty:.0f} MW"
    )
    
    # Add equilibrium point
    fig.add_trace(go.Scatter(
        x=[equilibrium_qty],
        y=[clearing_price],
        mode='markers',
        name='Market Clearing Point',
        marker=dict(color='green', size=15, symbol='star'),
        hovertemplate=(
            f"<b>Market Clearing Point</b><br>" +
            f"Price: ${clearing_price:.2f}/MWh<br>" +
            f"Quantity: {equilibrium_qty:.1f} MW<extra></extra>"
        )
    ))
    
    # Update layout
    fig.update_layout(
        title="Market Clearing Analysis with Economic Welfare",
        xaxis_title="Cumulative Quantity (MW)",
        yaxis_title="Price ($/MWh)",
        height=700,
        showlegend=True,
        hovermode='closest',
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        )
    )
    
    return fig, consumer_surplus, producer_surplus, total_cost

    """Create market clearing visualization with supply and demand curves"""
    fig = go.Figure()
    
    if not single_demand_mode and demand_bids:
        # Add retailer demand blocks
        cumulative_demand = 0
        sorted_demands = sorted(demand_bids, key=lambda x: x['price'], reverse=True)
        
        for demand in sorted_demands:
            is_satisfied = demand.get('satisfied', 0) > 0
            opacity = 1.0 if is_satisfied else 0.3
            
            fig.add_trace(go.Scatter(
                x=[cumulative_demand, cumulative_demand + demand['demand']],
                y=[demand['price'], demand['price']],
                name=f"{demand['retailer']} (Tier {demand['tier']})",
                line=dict(color='red', width=4),
                opacity=opacity,
                showlegend=True,
                hovertemplate=(
                    f"<b>{demand['retailer']}</b><br>" +
                    f"Tier: {demand['tier']}<br>" +
                    f"Price: ${demand['price']:.2f}/MWh<br>" +
                    f"Demand: {demand['demand']:.1f} MW<br>" +
                    f"Satisfied: {demand.get('satisfied', 0):.1f} MW<extra></extra>"
                )
            ))
            cumulative_demand += demand['demand']
    
    # Add generator blocks with dispatch status
    cumulative_supply = 0
    sorted_offers = sorted(dispatched_offers, key=lambda x: x['price'])
    
    for offer in sorted_offers:
        is_dispatched = offer['dispatched'] > 0
        opacity = 1.0 if is_dispatched else 0.3
        
        fig.add_trace(go.Scatter(
            x=[cumulative_supply, cumulative_supply + offer['capacity']],
            y=[offer['price'], offer['price']],
            name=f"{offer['generator']} (Tier {offer['tier']})",
            line=dict(color=offer['color'], width=6),
            opacity=opacity,
            showlegend=True,
            hovertemplate=(
                f"<b>{offer['generator']}</b><br>" +
                f"Tier: {offer['tier']}<br>" +
                f"Price: ${offer['price']:.2f}/MWh<br>" +
                f"Capacity: {offer['capacity']:.1f} MW<br>" +
                f"Dispatched: {offer['dispatched']:.1f} MW<extra></extra>"
            )
        ))
        
        # Add producer surplus shading for dispatched blocks
        if is_dispatched:
            fig.add_trace(go.Scatter(
                x=[cumulative_supply, cumulative_supply + offer['dispatched'], cumulative_supply + offer['dispatched']],
                y=[offer['price'], offer['price'], clearing_price],
                fill='tozeroy',
                fillcolor='rgba(173,216,230,0.3)',  # Light blue
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ))
        
        cumulative_supply += offer['capacity']
    
    # Add consumer surplus shading for satisfied demand
    if not single_demand_mode and satisfied_demands:
        for demand in sorted_demands:
            if demand.get('satisfied', 0) > 0:
                fig.add_trace(go.Scatter(
                    x=[cumulative_demand - demand['demand'], cumulative_demand],
                    y=[clearing_price, demand['price']],
                    fill='tonexty',
                    fillcolor='rgba(255,182,193,0.3)',  # Light pink
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo='skip'
                ))
    
    # Add clearing price line and vertical line at equilibrium
    fig.add_hline(
        y=clearing_price,
        line_color="green",
        line_width=2,
        line_dash="dash",
        annotation_text=f"Clearing Price: ${clearing_price:.2f}/MWh"
    )
    
    fig.add_vline(
        x=equilibrium_qty,
        line_color="green",
        line_width=2,
        line_dash="dash",
        annotation_text=f"Cleared Quantity: {equilibrium_qty:.0f} MW"
    )
    
    # Add equilibrium point
    fig.add_trace(go.Scatter(
        x=[equilibrium_qty],
        y=[clearing_price],
        mode='markers',
        name='Market Clearing',
        marker=dict(color='green', size=12, symbol='star'),
        hovertemplate=(
            f"<b>Market Clearing Point</b><br>" +
            f"Price: ${clearing_price:.2f}/MWh<br>" +
            f"Quantity: {equilibrium_qty:.1f} MW<extra></extra>"
        )
    ))
    
    # Update layout
    fig.update_layout(
        title="Market Clearing Analysis",
        xaxis_title="Cumulative Quantity (MW)",
        yaxis_title="Price ($/MWh)",
        height=600,
        showlegend=True,
        hovermode='closest'
    )
    
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

    st.title("Interactive Market Clearing")
    st.markdown("**Multi-tier bidding with comprehensive generator and demand analysis**")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Market Configuration")

        # Market mode selection
        market_mode = st.radio(
            "Market Mode",
            ["Multi-tier Bidding", "Single Demand Level"],
            help="Choose between complex bidding or simple demand level"
        )

        if market_mode == "Multi-tier Bidding":
            st.markdown("**3-Tier Bidding System**")
            st.info("Each generator offers 3 capacity tiers at increasing prices. Each retailer bids for 3 demand tiers at decreasing prices.")

            # Generate multi-tier offers and demands
            if st.button("Generate New Market", type="primary", key="generate_market"):
                # Force regenerate the offers and bids
                st.session_state.supply_offers = generate_multi_tier_offers()
                st.session_state.demand_bids = generate_multi_tier_demands()
                st.rerun()

            # Initialize if not exists
            if 'supply_offers' not in st.session_state:
                st.session_state.supply_offers = generate_multi_tier_offers()
            if 'demand_bids' not in st.session_state:
                st.session_state.demand_bids = generate_multi_tier_demands()

            # Find equilibrium
            dispatched_offers, satisfied_demands, clearing_price, equilibrium_qty = find_market_equilibrium_multi_tier(
                st.session_state.supply_offers, st.session_state.demand_bids, single_demand_mode=False
            )

        else:  # Single Demand Level
            st.markdown("**Single Demand Level**")
            total_demand = st.slider(
                "Total Market Demand (MW)",
                min_value=100,
                max_value=1500,
                value=600,
                step=50,
                help="Total electricity demand to be met by generators"
            )

            # Generate supply offers only
            if 'supply_offers' not in st.session_state:
                st.session_state.supply_offers = generate_multi_tier_offers()

            # Find equilibrium with single demand
            dispatched_offers, satisfied_demands, clearing_price, equilibrium_qty = find_market_equilibrium_multi_tier(
                st.session_state.supply_offers, [], single_demand_mode=True, total_demand=total_demand
            )

        # Create visualization with welfare analysis
        fig, consumer_surplus, producer_surplus, total_cost = create_market_clearing_plot(
            st.session_state.supply_offers, 
            st.session_state.demand_bids if market_mode == "Multi-tier Bidding" else [],
            dispatched_offers, satisfied_demands, clearing_price, equilibrium_qty,
            single_demand_mode=(market_mode == "Single Demand Level")
        )
        st.plotly_chart(fig, use_container_width=True, key="market_clearing_plot")

        # Detailed Results Tables
        st.subheader("📊 Detailed Market Results")

        # Generator Results Table
        if dispatched_offers:
            st.markdown("**Generator Dispatch Results**")
            gen_results = calculate_generator_metrics(dispatched_offers, clearing_price)
            gen_df = pd.DataFrame(gen_results)
            st.dataframe(gen_df, use_container_width=True)

        # Demand Results Table (only for multi-tier mode)
        if market_mode == "Multi-tier Bidding" and satisfied_demands:
            st.markdown("**Retailer Satisfaction Results**")
            demand_results = calculate_demand_metrics(satisfied_demands, clearing_price)
            demand_df = pd.DataFrame(demand_results)
            st.dataframe(demand_df, use_container_width=True)

    with col2:
        st.subheader("Market Results")

        # Display equilibrium metrics
        if clearing_price > 0:
            st.metric("Clearing Price", f"${clearing_price:.1f}/MWh")
            st.metric("Cleared Quantity", f"{equilibrium_qty:.0f} MW")

        # Economic Welfare Analysis Section
        st.subheader("💰 Economic Welfare Analysis")

        if market_mode == "Multi-tier Bidding":
            # Consumer Surplus
            st.metric(
                "Consumer Surplus", 
                f"${consumer_surplus:,.0f}",
                help="Net benefit to consumers (willingness to pay minus actual payment)"
            )

        # Producer Surplus (Scarcity Rent)
        st.metric(
            "Producer Surplus (Scarcity Rent)", 
            f"${producer_surplus:,.0f}",
            help="Generator profit above marginal cost"
        )

        # Total Generation Cost
        st.metric(
            "Total Generation Cost", 
            f"${total_cost:,.0f}",
            help="Total variable cost of electricity production"
        )

        if market_mode == "Multi-tier Bidding":
            # Total Welfare
            total_welfare = consumer_surplus + producer_surplus
            st.metric(
                "Total Economic Welfare", 
                f"${total_welfare:,.0f}",
                help="Sum of consumer and producer surplus"
            )

            # Market Efficiency Indicator
            total_payment = clearing_price * equilibrium_qty
            if total_payment > 0:
                efficiency_ratio = total_welfare / total_payment
                st.metric(
                    "Market Efficiency Ratio",
                    f"{efficiency_ratio:.2f}",
                    help="Total welfare relative to total payments"
                )

        # Market insights
        st.subheader("💡 Market Insights")

        if dispatched_offers:
            # Find marginal unit (last accepted bid)
            marginal_unit = None
            for offer in reversed(dispatched_offers):
                if offer['dispatched'] > 0:
                    marginal_unit = f"{offer['generator']} (Tier {offer['tier']})"
                    break

            if marginal_unit:
                st.markdown(f"**🎯 Price Setting Unit:** {marginal_unit}")

            # Technology mix analysis
            tech_dispatch = {}
            for offer in dispatched_offers:
                if offer['dispatched'] > 0:
                    tech_type = offer['type']
                    tech_dispatch[tech_type] = tech_dispatch.get(tech_type, 0) + offer['dispatched']

            st.markdown("**Technology Mix**")
            for tech, dispatch in tech_dispatch.items():
                pct = (dispatch / equilibrium_qty * 100) if equilibrium_qty > 0 else 0
                st.markdown(f"• **{tech}**: {dispatch:.0f} MW ({pct:.1f}%)")

            # Welfare insights
            if market_mode == "Multi-tier Bidding":
                if consumer_surplus > producer_surplus:
                    st.success("🛡️ Consumer-favorable market conditions")
                elif producer_surplus > consumer_surplus * 2:
                    st.warning("⚡ High scarcity rents - tight supply conditions")
                else:
                    st.info("⚖️ Balanced welfare distribution")

            # Price insights
            if clearing_price == 0:
                st.success("🌱 Zero-cost renewables setting market price!")
            elif clearing_price < 50:
                st.info("💚 Low-cost generation dominating market")
            elif clearing_price > 100:
                st.warning("⚡ High prices indicate scarcity or peaking generation")

        # Control buttons
        st.subheader("🔄 Market Controls")

        if st.button("Reset Market", type="secondary", key="reset_market"):
            if 'supply_offers' in st.session_state:
                del st.session_state.supply_offers
            if 'demand_bids' in st.session_state:
                del st.session_state.demand_bids
            st.rerun()

        if market_mode == "Multi-tier Bidding":
            st.markdown("**Market Mode**: Complex bidding with multiple tiers")
        else:
            st.markdown(f"**Market Mode**: Single demand level ({total_demand if 'total_demand' in locals() else 'N/A'} MW)")

        # Show bid/offer summary
        if 'supply_offers' in st.session_state:
            total_supply_capacity = sum(offer['capacity'] for offer in st.session_state.supply_offers)
            st.metric("Total Supply Capacity", f"{total_supply_capacity:.0f} MW")

            if market_mode == "Multi-tier Bidding" and 'demand_bids' in st.session_state:
                total_demand_bids = sum(bid['demand'] for bid in st.session_state.demand_bids)
                st.metric("Total Demand Bids", f"{total_demand_bids:.0f} MW")

    with st.expander("📚 Educational Content"):
        st.markdown("""
        ### Market Equilibrium and Welfare Analysis

        **Market Equilibrium**:
        - Intersection point of supply and demand curves
        - Determines market clearing price and quantity
        - Maximizes total economic welfare (Pareto efficiency)

        **Economic Welfare Measures**:
        - **Consumer Surplus**: Benefit to consumers above what they pay
        - **Producer Surplus**: Benefit to suppliers above their costs
        - **Total Welfare**: Sum of consumer and producer surplus
        - **Deadweight Loss**: Welfare reduction from non-equilibrium outcomes

        **Mathematical Relationships**:
        - Consumer Surplus = 0.5 × Quantity × (Demand Intercept - Price)
        - Producer Surplus = 0.5 × Quantity × (Price - Supply Intercept)
        - Equilibrium where: Supply Price = Demand Price

        ### Interactive Learning:
        - Adjust supply and demand parameters to see effects
        - Observe how curve slopes affect equilibrium
        - Understand relationship between elasticity and welfare
        - Connect theory to electricity market applications            
        ### Applications in Electricity Markets:
        - Models spot market price formation
        - Shows welfare implications of market interventions
        - Demonstrates efficiency of competitive markets
        - Helps understand impact of demand response and storage
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
