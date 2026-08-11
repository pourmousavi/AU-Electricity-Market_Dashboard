### Interactive Market Clearing - Enhanced Features        
            # **Multi-Tier Bidding System**:
            # - **3-Tier Generator Offers**: Each generator submits 3 capacity blocks at increasing prices
            # - **3-Tier Demand Bids**: Each retailer bids for 3 demand blocks at decreasing willingness to pay
            # - **Realistic Market Structure**: Mirrors actual electricity market bidding processes
            
            # **Two Operating Modes**:
            
            # **1. Multi-Tier Bidding Mode**:
            # - Complex bidding with 4 retailers each submitting 3-tier demand bids
            # - 12 generators each offering 3-tier capacity blocks
            # - Automatic market clearing finds equilibrium price and quantity
            # - Shows both supply and demand stacks
            
            # **2. Single Demand Level Mode**:
            # - Simplified mode with user-controlled total demand slider
            # - Focuses on supply-side dispatch and generator economics
            # - No demand bidding - just meet specified demand level
            # - Easier for understanding merit order dispatch
            
            # **Comprehensive Results Analysis**:
            
            # **Generator Dispatch Table**:
            # - Individual tier dispatch quantities (MW and %)
            # - Bid prices vs clearing price
            # - Revenue, cost, and scarcity rent calculations
            # - Technology mix breakdown
            
            # **Retailer Satisfaction Table** (Multi-tier mode):
            # - Satisfied demand by tier (MW and %)
            # - Expenses vs willingness to pay
            # - Net surplus calculations
            # - Consumer welfare analysis
            
            # **Market Insights**:
            # - **Technology Mix**: Renewable vs fossil dispatch percentages
            # - **Price Signals**: Zero-cost renewables vs scarcity pricing
            # - **Efficiency Indicators**: Low-cost vs high-cost generation utilization
            # - **Market Mode Comparison**: Complex bidding vs simple demand level
            
            # **Educational Value**:
            # - **Realistic Bidding**: Multi-tier structure reflects actual electricity markets
            # - **Economic Analysis**: Detailed generator and retailer financial metrics
            # - **Technology Impact**: Shows how different generation types affect clearing
            # - **Market Design**: Compare complex vs simplified market structures
            
            # **Real-World Applications**:
            # - Models Australian NEM spot market structure
            # - Shows impact of renewable integration on clearing prices
            # - Demonstrates storage arbitrage opportunities
            # - Illustrates scarcity pricing during high demand periods
            
            # **Key Learning Outcomes**:
            # - Understand multi-tier bidding complexity vs simplified demand
            # - Analyze generator economics including scarcity rent
            # - Evaluate retailer welfare and consumer surplus
            # - Compare technology dispatch patterns and market efficiency            **Enhanced Investment Analysis Features**:
            
            # **Expanded Cost Range**: 
            # - Marginal costs now range from $0 to $1,000/MWh
            # - Reflects real-world emergency and scarcity pricing
            # - Models extreme peaking units and backup generators
            
            # **Capacity Factor as Input**:
            # - User-controlled capacity factor (5-95%) via slider
            # - Represents expected plant utilization based on technology type
            # - Baseload plants: 80-95%, Peaking plants: 5-20%, Storage: 10-40%
            
            # **Comprehensive Financial Metrics**:
            # - **Total Revenue**: Annual income from electricity sales
            # - **Variable Costs**: Operating costs (fuel, maintenance)
            # - **Short-run Profit**: Revenue minus variable costs (scarcity rent)
            # - **Long-run Profit**: Includes fixed cost recovery and required return
            # - **Required vs Actual Rate of Return**: Investment viability indicator
            
            # **Results Summary Table**:
            # All analysis scenarios displayed in comprehensive table showing:
            # - Plant specifications (capacity, marginal cost, capacity factor)
            # - Financial performance (revenues, costs, profits)
            # - Investment returns (required vs actual RoR)
            # - Viability assessment (✅/❌)
            
            # **Investment Decision Framework**:
            # - **Viable Investment**: Actual RoR >= Required RoR
            # - **Market Price Assumptions**: Based on marginal cost positioning
            # - **Technology Implications**: Different capacity factors for different tech types
            
            # **Real-World Applications**:
            # - **Emergency/Backup Plants**: $500-1000/MWh, low capacity factors
            # - **Peaking Gas Turbines**: $100-300/MWh, 10-20% capacity factor
            # - **Storage Systems**: Variable costs, arbitrage opportunities
            # - **Renewable + Storage**: Combined investment analysis
            
            # **Key Learning Points**:
            # - High marginal cost units require scarcity pricing for viability
            # - Capacity factor critically affects investment returns
            # - Rate of return analysis shows risk-adjusted profitability
            # - Fixed cost recovery through energy market participation
            
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Configure the page - matching the original dashboard style
st.set_page_config(
    page_title="Electricity Market Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# Sidebar navigation - matching original style
st.sidebar.title("⚡ Electricity Market Dashboard")
st.sidebar.markdown("---")

# Navigation menu - matching original structure
page = st.sidebar.selectbox(
    "Select Analysis Tool:",
    ["Pool Market Pricing", "Market Power Analysis", "Profit & Cost Recovery", "Interactive Market Clearing"]
)

# Course information and credits - exactly matching original
st.sidebar.markdown("---")
st.sidebar.markdown("### Course Information")
st.sidebar.markdown("**Electricity Market and Power Systems Operation**")
st.sidebar.markdown("**ELEC ENG 4087/7087**")
st.sidebar.markdown("---")
st.sidebar.markdown("**Course Coordinator & Creator:**")
st.sidebar.markdown("Ali Pourmousavi Kani")
st.sidebar.markdown("---")
st.sidebar.markdown("**Version:** 1.0 - Market Power & Economics")

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

def calculate_competition_models(mc_a, mc_b, demand_intercept=100):
    """Calculate outcomes for perfect competition, Bertrand, and Cournot models"""
    
    # Perfect Competition
    mcp = min(mc_a, mc_b)
    pc_demand = demand_intercept - mcp
    if mc_a < mc_b:
        pc_pa = min(pc_demand, 100)  # Capacity limit
        pc_pb = max(0, pc_demand - pc_pa)
    elif mc_b < mc_a:
        pc_pb = min(pc_demand, 100)
        pc_pa = max(0, pc_demand - pc_pb)
    else:
        pc_pa = pc_pb = pc_demand / 2
    
    # Bertrand Competition
    if mc_a < mc_b:
        bert_price = mc_b - 0.01
        bert_demand = demand_intercept - bert_price
        bert_pa = bert_demand
        bert_pb = 0
    elif mc_b < mc_a:
        bert_price = mc_a - 0.01
        bert_demand = demand_intercept - bert_price
        bert_pa = 0
        bert_pb = bert_demand
    else:
        bert_price = mc_a
        bert_demand = demand_intercept - bert_price
        bert_pa = bert_pb = bert_demand / 2
    
    # Cournot Competition (from lecture slides)
    if mc_a == 36 and mc_b == 46:
        cour_pa = 24.7
        cour_pb = 14.7
    else:
        # General solution
        a_coeff = demand_intercept - mc_a
        b_coeff = demand_intercept - mc_b
        cour_pa = max(0, (2 * a_coeff - b_coeff) / 3)
        cour_pb = max(0, (2 * b_coeff - a_coeff) / 3)
    
    cour_demand = cour_pa + cour_pb
    cour_price = demand_intercept - cour_demand
    
    return {
        'perfect_competition': {'pa': pc_pa, 'pb': pc_pb, 'demand': pc_demand, 'price': mcp},
        'bertrand': {'pa': bert_pa, 'pb': bert_pb, 'demand': bert_demand, 'price': bert_price},
        'cournot': {'pa': cour_pa, 'pb': cour_pb, 'demand': cour_demand, 'price': cour_price}
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

def create_market_power_plot(mc_a, mc_b, analysis_points):
    """Create market power comparison plot with improved legends and labels"""
    results = calculate_competition_models(mc_a, mc_b)
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Production by Firm", "Price Comparison", 
                       "Market Equilibrium Points", "Competition Model Comparison"),
        specs=[[{"type": "bar"}, {"type": "bar"}],
               [{"type": "scatter"}, {"type": "scatter"}]]
    )
    
    # Top left: Production comparison by firm
    models = ["Perfect Competition", "Bertrand", "Cournot"]
    firm_a_production = [results['perfect_competition']['pa'], results['bertrand']['pa'], results['cournot']['pa']]
    firm_b_production = [results['perfect_competition']['pb'], results['bertrand']['pb'], results['cournot']['pb']]
    
    fig.add_trace(go.Bar(x=models, y=firm_a_production, name="Firm A Production", 
                        marker_color='#FF6B6B', 
                        text=[f"{p:.1f}" for p in firm_a_production],
                        textposition="outside",
                        legendgroup="production"), row=1, col=1)
    
    fig.add_trace(go.Bar(x=models, y=firm_b_production, name="Firm B Production", 
                        marker_color='#4ECDC4', 
                        text=[f"{p:.1f}" for p in firm_b_production],
                        textposition="outside",
                        legendgroup="production"), row=1, col=1)
    
    # Top right: Price comparison 
    prices = [results['perfect_competition']['price'], results['bertrand']['price'], results['cournot']['price']]
    colors_price = ['#2E8B57', '#FF8C00', '#8A2BE2']
    
    fig.add_trace(go.Bar(x=models, y=prices, name="Market Price", 
                        marker_color=colors_price,
                        text=[f"${p:.1f}" for p in prices],
                        textposition="outside", 
                        showlegend=False,
                        legendgroup="price"), row=1, col=2)
    
    # Bottom left: Market equilibrium visualization
    quantities = np.linspace(0, 80, 100)
    demand_prices = 100 - quantities
    
    fig.add_trace(go.Scatter(x=quantities, y=demand_prices, mode='lines',
                           name='Inverse Demand Curve', 
                           line=dict(color='blue', width=3),
                           legendgroup="curves"), row=2, col=1)
    
    # Add competition model points with distinct markers
    model_info = [
        ('perfect_competition', 'Perfect Competition', 'circle', '#2E8B57'),
        ('bertrand', 'Bertrand Model', 'square', '#FF8C00'),
        ('cournot', 'Cournot Model', 'diamond', '#8A2BE2')
    ]
    
    for model_key, model_name, symbol, color in model_info:
        data = results[model_key]
        fig.add_trace(go.Scatter(
            x=[data['demand']], y=[data['price']],
            mode='markers', name=model_name,
            marker=dict(color=color, size=12, symbol=symbol),
            hovertemplate=f"<b>{model_name}</b><br>" +
                         f"Quantity: {data['demand']:.1f} MW<br>" +
                         f"Price: ${data['price']:.1f}/MWh<extra></extra>",
            legendgroup="models"
        ), row=2, col=1)
    
    # Bottom right: Total quantity vs price comparison
    total_quantities = [results['perfect_competition']['demand'], 
                       results['bertrand']['demand'], 
                       results['cournot']['demand']]
    
    fig.add_trace(go.Scatter(x=total_quantities, y=prices, mode='markers+lines',
                           name='Model Outcomes', 
                           marker=dict(size=10, color=colors_price),
                           line=dict(color='gray', dash='dash'),
                           showlegend=False), row=2, col=2)
    
    # Add model labels to bottom right plot
    for i, (qty, price, model) in enumerate(zip(total_quantities, prices, models)):
        fig.add_annotation(
            x=qty, y=price,
            text=model.split()[0],  # Just first word
            showarrow=True,
            arrowhead=2,
            row=2, col=2
        )
    
    # Analysis points
    for i, point in enumerate(analysis_points):
        fig.add_trace(go.Scatter(
            x=[point['total_quantity']], y=[point['market_price']],
            mode='markers', name=f'Analysis {i+1}',
            marker=dict(color='red', size=10, symbol='star'),
            showlegend=False
        ), row=2, col=1)
    
    # Update layout and axis labels
    fig.update_layout(height=700, title_text="Market Power Analysis - Competition Models")
    
    # Axis labels for all subplots
    fig.update_xaxes(title_text="Competition Models", row=1, col=1)
    fig.update_yaxes(title_text="Production (MW)", row=1, col=1)
    fig.update_xaxes(title_text="Competition Models", row=1, col=2)
    fig.update_yaxes(title_text="Price ($/MWh)", row=1, col=2)
    fig.update_xaxes(title_text="Quantity (MW)", row=2, col=1)
    fig.update_yaxes(title_text="Price ($/MWh)", row=2, col=1)
    fig.update_xaxes(title_text="Total Quantity (MW)", row=2, col=2)
    fig.update_yaxes(title_text="Market Price ($/MWh)", row=2, col=2)
    
    return fig

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

# Main sections matching original structure
def pool_market_pricing_section():
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

def market_power_analysis_section():
    st.title("Market Power Analysis")
    st.markdown("**Chapter 2.12: Compare Perfect Competition, Bertrand, and Cournot models**")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Duopoly Market Configuration")
        st.markdown("**Based on Lecture Example (Slides 26-32)**")
        
        # Firm cost inputs - matching course example
        mc_a = st.number_input(
            "Firm A Marginal Cost ($/MWh)",
            min_value=10,
            max_value=80,
            value=36,
            step=1,
            help="From lecture: CA = 36*PA"
        )
        
        mc_b = st.number_input(
            "Firm B Marginal Cost ($/MWh)",
            min_value=10,
            max_value=80,
            value=46,
            step=1,
            help="From lecture: CB = 46*PB"
        )
        
        # Create plot
        fig = create_market_power_plot(mc_a, mc_b, st.session_state.market_power_data)
        st.plotly_chart(fig, use_container_width=True, key="market_power_plot")
        
        # Analysis
        if st.button("Analyze Current Configuration", type="primary", key="market_power_add"):
            results = calculate_competition_models(mc_a, mc_b)
            
            # Calculate market power metrics
            pc_total = results['perfect_competition']['demand']
            cour_total = results['cournot']['demand']
            market_power_index = (pc_total - cour_total) / pc_total * 100 if pc_total > 0 else 0
            
            st.session_state.market_power_data.append({
                'mc_a': mc_a,
                'mc_b': mc_b,
                'pc_price': results['perfect_competition']['price'],
                'bert_price': results['bertrand']['price'],
                'cour_price': results['cournot']['price'],
                'total_quantity': cour_total,
                'market_price': results['cournot']['price'],
                'market_power_index': market_power_index
            })
            st.rerun()
    
    with col2:
        st.subheader("Competition Results")
        
        # Calculate and display current results
        results = calculate_competition_models(mc_a, mc_b)
        
        # Results table - course format
        results_df = pd.DataFrame({
            'Model': ['Perfect Competition', 'Bertrand', 'Cournot'],
            'Firm A (MW)': [f"{results['perfect_competition']['pa']:.1f}", 
                           f"{results['bertrand']['pa']:.1f}", 
                           f"{results['cournot']['pa']:.1f}"],
            'Firm B (MW)': [f"{results['perfect_competition']['pb']:.1f}", 
                           f"{results['bertrand']['pb']:.1f}", 
                           f"{results['cournot']['pb']:.1f}"],
            'Price ($/MWh)': [f"{results['perfect_competition']['price']:.1f}", 
                             f"{results['bertrand']['price']:.1f}", 
                             f"{results['cournot']['price']:.1f}"]
        })
        
        st.dataframe(results_df, use_container_width=True)
        
        # Key insights
        st.subheader("Market Power Insights")
        cour_premium = results['cournot']['price'] - results['perfect_competition']['price']
        st.metric("Cournot Price Premium", f"${cour_premium:.1f}/MWh")
        
        quantity_reduction = results['perfect_competition']['demand'] - results['cournot']['demand']
        st.metric("Quantity Withholding", f"{quantity_reduction:.1f} MW")

def profit_cost_recovery_section():
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

def interactive_market_clearing_section():
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

# Main section router - matching original structure
if page == "Pool Market Pricing":
    pool_market_pricing_section()
elif page == "Market Power Analysis":
    market_power_analysis_section()
elif page == "Profit & Cost Recovery":
    profit_cost_recovery_section()
elif page == "Interactive Market Clearing":
    interactive_market_clearing_section()

# Educational content section - matching original expandable format
def main():
    with st.expander("📚 Educational Content"):
        if page == "Pool Market Pricing":
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
        
        elif page == "Market Power Analysis":
            st.markdown("""
            ### Market Power in Electricity Markets (Chapter 2.12)
            
            **Market Power Definition**: 
            "The ability to alter profitably prices away from competitive levels"
            
            **Three Competition Models**:
            
            **1. Perfect Competition**:
            - Many small firms, price takers
            - Price equals marginal cost
            - Maximum economic efficiency
            - Baseline for comparison
            
            **2. Bertrand Competition**:
            - Firms compete on price
            - Winner-takes-all market structure
            - Results closer to perfect competition
            - Price competition is fierce
            
            **3. Cournot Competition**:
            - Firms compete on quantity
            - Strategic capacity withholding
            - Higher prices than perfect competition
            - Models market power through production decisions
            
            ### Course Example (Slides 26-32):
            - Firm A: $36/MWh marginal cost
            - Firm B: $46/MWh marginal cost
            - Inverse demand: π = 100 - D
            - Mathematical solution shows different outcomes under each model
            
            ### Real-World Examples:
            - **California ISO**: "Must-run" generators with market power
            - **Load Pockets**: San Francisco, New York with local market power
            - **Australian NEM**: Traditional plants exercising power during evening peaks
            """)
        
               
        elif page == "Profit & Cost Recovery":
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
        
        elif page == "Interactive Market Clearing":
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

# Call main function to show educational content
main()

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