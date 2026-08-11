import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# Configure the page
st.set_page_config(
    page_title="Electricity Market Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'click_data' not in st.session_state:
    st.session_state.click_data = []
if 'elasticity_data' not in st.session_state:
    st.session_state.elasticity_data = []
if 'supplier_click_data' not in st.session_state:
    st.session_state.supplier_click_data = []
if 'supplier_elasticity_data' not in st.session_state:
    st.session_state.supplier_elasticity_data = []
if 'market_analysis_data' not in st.session_state:
    st.session_state.market_analysis_data = []
if 'supply_bids' not in st.session_state:
    st.session_state.supply_bids = []
if 'demand_bids' not in st.session_state:
    st.session_state.demand_bids = []

# Sidebar navigation
st.sidebar.title("⚡ Electricity Market Dashboard")
st.sidebar.markdown("---")

# Navigation menu
page = st.sidebar.selectbox(
    "Select Analysis Tool:",
    ["Consumer Model", "Consumer Elasticity", "Supplier Model", "Supplier Elasticity", "Market Equilibrium"]
)

# Course information and credits
st.sidebar.markdown("---")
st.sidebar.markdown("### Course Information")
st.sidebar.markdown("**Electricity Market and Power Systems Operation**")
st.sidebar.markdown("**ELEC ENG 4087/7087**")
st.sidebar.markdown("---")
st.sidebar.markdown("**Course Coordinator & Creator:**")
st.sidebar.markdown("Ali Pourmousavi Kani")
st.sidebar.markdown("---")
st.sidebar.markdown("**Version:** 2.0")

def calculate_areas(intercept, slope, price, quantity):
    """Calculate gross surplus, expenses, and net surplus for consumer"""
    # Gross surplus (total area under demand curve from 0 to quantity)
    # This is the integral of the demand function: ∫(intercept + slope*q)dq from 0 to quantity
    gross_surplus = intercept * quantity + 0.5 * slope * quantity**2
    
    # Consumer expenses (rectangle area)
    expenses = price * quantity
    
    # Net surplus = Gross surplus - expenses (the actual consumer surplus)
    net_surplus = gross_surplus - expenses
    
    return gross_surplus, expenses, net_surplus

def calculate_supplier_areas(intercept, slope, price, quantity):
    """Calculate revenue, cost, and profit for supplier"""
    # Revenue (rectangle area: price × quantity)
    revenue = price * quantity
    
    # Cost (area under supply curve from 0 to quantity)
    # This is the integral of the supply function: ∫(intercept + slope*q)dq from 0 to quantity
    cost = intercept * quantity + 0.5 * slope * quantity**2
    
    # Profit = Revenue - Cost (the actual producer surplus)
    profit = revenue - cost
    
    return revenue, cost, profit

def calculate_elasticity(intercept, slope, quantity, price):
    """Calculate price elasticity of demand/supply at a given point"""
    # Price elasticity = (dQ/dP) * (P/Q)
    # For linear demand/supply: P = intercept + slope * Q
    # dP/dQ = slope, so dQ/dP = 1/slope
    # Elasticity = (1/slope) * (P/Q)
    
    if quantity == 0 or slope == 0:
        return float('inf')  # Infinite elasticity at zero quantity or zero slope
    
    elasticity = (1/slope) * (price/quantity)
    return elasticity

def generate_supply_bids(num_bids=10, max_quantity=100, min_price=10, max_price=100):
    """Generate random supply bid stack (monotonically increasing prices)"""
    # Generate random quantities
    quantities = np.random.uniform(5, max_quantity/num_bids, num_bids)
    quantities = np.round(quantities, 1)
    
    # Generate monotonically increasing prices
    prices = np.sort(np.random.uniform(min_price, max_price, num_bids))
    prices = np.round(prices, 1)
    
    # Create cumulative quantities for step function
    cumulative_quantities = np.cumsum(quantities)
    
    supply_bids = []
    for i in range(num_bids):
        supply_bids.append({
            'bid_id': i + 1,
            'quantity': quantities[i],
            'price': prices[i],
            'cumulative_quantity': cumulative_quantities[i]
        })
    
    return supply_bids

def generate_demand_bids(num_bids=10, max_quantity=100, min_price=20, max_price=120):
    """Generate random demand bid stack (monotonically decreasing prices)"""
    # Generate random quantities
    quantities = np.random.uniform(5, max_quantity/num_bids, num_bids)
    quantities = np.round(quantities, 1)
    
    # Generate monotonically decreasing prices
    prices = np.sort(np.random.uniform(min_price, max_price, num_bids))[::-1]
    prices = np.round(prices, 1)
    
    # Create cumulative quantities for step function
    cumulative_quantities = np.cumsum(quantities)
    
    demand_bids = []
    for i in range(num_bids):
        demand_bids.append({
            'bid_id': i + 1,
            'quantity': quantities[i],
            'price': prices[i],
            'cumulative_quantity': cumulative_quantities[i]
        })
    
    return demand_bids

def find_market_equilibrium(supply_bids, demand_bids):
    """Find market clearing price and quantity"""
    if not supply_bids or not demand_bids:
        return 0, 0
    
    equilibrium_qty = 0
    equilibrium_price = 0
    
    # Check intersections at each supply and demand quantity point
    all_supply_qtys = [bid['cumulative_quantity'] for bid in supply_bids]
    all_demand_qtys = [bid['cumulative_quantity'] for bid in demand_bids]
    all_qtys = sorted(set(all_supply_qtys + all_demand_qtys))
    
    for qty in all_qtys:
        if qty == 0:
            continue
            
        # Find supply price at this quantity
        supply_price = float('inf')
        for bid in supply_bids:
            if qty <= bid['cumulative_quantity']:
                supply_price = bid['price']
                break
        
        # Find demand price at this quantity
        demand_price = 0
        for bid in demand_bids:
            if qty <= bid['cumulative_quantity']:
                demand_price = bid['price']
                break
        
        # Check if market can clear at this quantity
        if demand_price >= supply_price and supply_price != float('inf'):
            equilibrium_qty = qty
            
            # Determine price based on which curve creates the intersection
            if qty in all_supply_qtys and qty not in all_demand_qtys:
                # Intersection at supply step (supply vertical, demand horizontal)
                # Use demand price - buyers set the market price
                equilibrium_price = demand_price
            elif qty in all_demand_qtys and qty not in all_supply_qtys:
                # Intersection at demand step (demand vertical, supply horizontal)  
                # Use supply price - sellers set the market price
                equilibrium_price = supply_price
            else:
                # Both curves step at same quantity or other cases
                # Use supply price (marginal cost principle)
                equilibrium_price = supply_price
        else:
            # No longer feasible, we've found the maximum clearing quantity
            break
    
    return equilibrium_qty, equilibrium_price

def calculate_market_welfare(supply_bids, demand_bids, market_price, market_quantity):
    """Calculate consumer surplus, producer surplus, and total welfare"""
    consumer_surplus = 0
    producer_surplus = 0
    
    if market_quantity <= 0:
        return 0, 0, 0
    
    # Calculate consumer surplus - sum of (bid_price - market_price) * quantity for accepted demand bids
    cumulative_qty = 0
    for bid in demand_bids:
        if cumulative_qty >= market_quantity:
            break
            
        # Determine how much of this bid is accepted
        bid_start_qty = cumulative_qty
        bid_end_qty = min(bid['cumulative_quantity'], market_quantity)
        accepted_qty = bid_end_qty - bid_start_qty
        
        if accepted_qty > 0 and bid['price'] > market_price:
            consumer_surplus += (bid['price'] - market_price) * accepted_qty
        
        cumulative_qty = bid['cumulative_quantity']
    
    # Calculate producer surplus - sum of (market_price - bid_price) * quantity for accepted supply bids
    cumulative_qty = 0
    for bid in supply_bids:
        if cumulative_qty >= market_quantity:
            break
            
        # Determine how much of this bid is accepted
        bid_start_qty = cumulative_qty
        bid_end_qty = min(bid['cumulative_quantity'], market_quantity)
        accepted_qty = bid_end_qty - bid_start_qty
        
        if accepted_qty > 0 and market_price > bid['price']:
            producer_surplus += (market_price - bid['price']) * accepted_qty
        
        cumulative_qty = bid['cumulative_quantity']
    
    total_welfare = consumer_surplus + producer_surplus
    
    return consumer_surplus, producer_surplus, total_welfare

def create_consumer_model_plot(intercept, slope, clicked_points):
    """Create the consumer demand curve plot with areas"""
    # Generate demand curve points
    max_quantity = intercept / abs(slope)
    quantities = np.linspace(0, max_quantity * 1.1, 100)
    prices = intercept + slope * quantities
    
    # Create the main plot
    fig = go.Figure()
    
    # Add demand curve
    fig.add_trace(go.Scatter(
        x=quantities,
        y=prices,
        mode='lines',
        name='Demand Curve',
        line=dict(color='blue', width=3),
        hovertemplate='Quantity: %{x:.2f}<br>Price: %{y:.2f}<extra></extra>'
    ))
    
    # Add clicked points and areas
    area_colors = [
        ('rgba(255, 99, 71, 0.4)', 'rgba(50, 205, 50, 0.4)'),     # Red expenses, Green net surplus
        ('rgba(255, 165, 0, 0.4)', 'rgba(0, 191, 255, 0.4)'),     # Orange expenses, Deep sky blue net surplus
        ('rgba(138, 43, 226, 0.4)', 'rgba(255, 20, 147, 0.4)'),   # Blue violet expenses, Deep pink net surplus
        ('rgba(255, 215, 0, 0.4)', 'rgba(32, 178, 170, 0.4)'),    # Gold expenses, Light sea green net surplus
        ('rgba(220, 20, 60, 0.4)', 'rgba(127, 255, 212, 0.4)'),   # Crimson expenses, Aquamarine net surplus
        ('rgba(75, 0, 130, 0.4)', 'rgba(255, 182, 193, 0.4)')     # Indigo expenses, Light pink net surplus
    ]
    marker_colors = ['red', 'orange', 'blueviolet', 'gold', 'crimson', 'indigo']
    
    for i, point in enumerate(clicked_points):
        quantity, price = point['quantity'], point['price']
        expense_color, net_color = area_colors[i % len(area_colors)]
        marker_color = marker_colors[i % len(marker_colors)]
        
        # Add horizontal and vertical reference lines for this point
        fig.add_hline(y=price, line_dash="dot", line_color="gray", opacity=0.3)
        fig.add_vline(x=quantity, line_dash="dot", line_color="gray", opacity=0.3)
        
        # Expenses area (rectangle: bottom-left is origin, top-right is (quantity, price))
        fig.add_trace(go.Scatter(
            x=[0, quantity, quantity, 0, 0],
            y=[0, 0, price, price, 0],
            fill='toself',
            fillcolor=expense_color,
            mode='none',
            name=f'Expenses {i+1}',
            showlegend=True,  # Show all expenses in legend
            line=dict(width=0),
            legendgroup=f'point{i+1}',  # Group legend items by point
            legendgrouptitle_text=f"Point {i+1}" if i < 3 else None  # Only show group title for first few
        ))
        
        # Net surplus area (triangle: vertices at (0,price), (quantity,price), (0,intercept))
        # This is the area between the demand line and the horizontal price line
        fig.add_trace(go.Scatter(
            x=[0, quantity, 0, 0],
            y=[price, price, intercept, price],
            fill='toself',
            fillcolor=net_color,
            mode='none',
            name=f'Net Surplus {i+1}',
            showlegend=True,  # Show all net surplus in legend
            line=dict(width=0),
            legendgroup=f'point{i+1}',  # Group legend items by point
        ))
        
        # Add the analysis point ON the demand curve
        # Point is always at (quantity, price) which should be on the demand curve by design
        fig.add_trace(go.Scatter(
            x=[quantity],
            y=[price],
            mode='markers',
            name=f'Analysis Point {i+1}',
            marker=dict(
                color=marker_color, 
                size=12, 
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            legendgroup=f'point{i+1}',  # Group with the areas for this point
            hovertemplate=(
                f'<b>Point {i+1}</b><br>' +
                f'Quantity: {quantity:.1f} MWh<br>' +
                f'Price: ${price:.1f}/MWh<br>' +
                f'<br><b>Economic Analysis:</b><br>' +
                f'Gross Surplus: ${point.get("gross_surplus", 0):.0f}<br>' +
                f'Expenses: ${point.get("expenses", 0):.0f} ({point.get("exp_percentage", 0):.1f}% of GS)<br>' +
                f'Net Surplus: ${point.get("net_surplus", 0):.0f} ({point.get("net_percentage", 0):.1f}% of GS)<br>' +
                '<extra></extra>'
            )
        ))
    
    # Update layout
    fig.update_layout(
        title='Consumer Demand Model',
        xaxis_title='Quantity (MWh)',
        yaxis_title='Price ($/MWh)',
        hovermode='closest',
        height=600,
        showlegend=True,
        xaxis=dict(range=[0, max_quantity * 1.1]),
        yaxis=dict(range=[0, intercept * 1.1])
    )
    
    return fig

def create_market_equilibrium_plot(supply_bids, demand_bids, analysis_points):
    """Create market equilibrium plot with supply/demand curves and welfare areas"""
    fig = go.Figure()
    
    if not supply_bids or not demand_bids:
        fig.update_layout(
            title='Market Equilibrium - Generate Bids First',
            xaxis_title='Quantity (MWh)',
            yaxis_title='Price ($/MWh)',
            height=600
        )
        return fig
    
    # Create supply curve (step function)
    supply_x = [0]
    supply_y = [supply_bids[0]['price']]
    
    prev_qty = 0
    for bid in supply_bids:
        # Horizontal line at current price
        supply_x.append(bid['cumulative_quantity'])
        supply_y.append(bid['price'])
        # Vertical line to next price (if not last bid)
        if bid != supply_bids[-1]:
            supply_x.append(bid['cumulative_quantity'])
            supply_y.append(supply_bids[supply_bids.index(bid) + 1]['price'])
    
    # Extend supply curve
    max_qty = max(supply_bids[-1]['cumulative_quantity'], demand_bids[-1]['cumulative_quantity'])
    supply_x.append(max_qty * 1.2)
    supply_y.append(supply_bids[-1]['price'])
    
    # Create demand curve (step function)
    demand_x = [0]
    demand_y = [demand_bids[0]['price']]
    
    for bid in demand_bids:
        # Horizontal line at current price
        demand_x.append(bid['cumulative_quantity'])
        demand_y.append(bid['price'])
        # Vertical line to next price (if not last bid)
        if bid != demand_bids[-1]:
            demand_x.append(bid['cumulative_quantity'])
            demand_y.append(demand_bids[demand_bids.index(bid) + 1]['price'])
    
    # Extend demand curve to x-axis
    demand_x.append(max_qty * 1.2)
    demand_y.append(0)
    
    # Add supply curve
    fig.add_trace(go.Scatter(
        x=supply_x,
        y=supply_y,
        mode='lines',
        name='Supply Curve',
        line=dict(color='red', width=3),
        hovertemplate='Quantity: %{x:.1f}<br>Price: $%{y:.1f}<extra></extra>'
    ))
    
    # Add demand curve
    fig.add_trace(go.Scatter(
        x=demand_x,
        y=demand_y,
        mode='lines',
        name='Demand Curve',
        line=dict(color='blue', width=3),
        hovertemplate='Quantity: %{x:.1f}<br>Price: $%{y:.1f}<extra></extra>'
    ))
    
    # Find and show equilibrium
    eq_qty, eq_price = find_market_equilibrium(supply_bids, demand_bids)
    
    if eq_qty > 0 and eq_price > 0:
        # Calculate welfare at equilibrium
        eq_cs, eq_ps, eq_total_welfare = calculate_market_welfare(supply_bids, demand_bids, eq_price, eq_qty)
        
        # Add equilibrium point
        fig.add_trace(go.Scatter(
            x=[eq_qty],
            y=[eq_price],
            mode='markers',
            name='Market Equilibrium',
            marker=dict(color='black', size=15, symbol='diamond'),
            hovertemplate=(
                f'<b>Market Equilibrium</b><br>' +
                f'Quantity: {eq_qty:.1f} MWh<br>' +
                f'Price: ${eq_price:.1f}/MWh<br>' +
                f'<br><b>Market Welfare:</b><br>' +
                f'Consumer Surplus: ${eq_cs:.0f}<br>' +
                f'Producer Surplus: ${eq_ps:.0f}<br>' +
                f'Total Welfare: ${eq_total_welfare:.0f}<br>' +
                '<extra></extra>'
            )
        ))
        
        # Add equilibrium lines
        fig.add_hline(y=eq_price, line_dash="dash", line_color="black", opacity=0.5)
        fig.add_vline(x=eq_qty, line_dash="dash", line_color="black", opacity=0.5)
        
        # Calculate and show welfare areas
        cs, ps, total_welfare = calculate_market_welfare(supply_bids, demand_bids, eq_price, eq_qty)
        
        # Add consumer surplus areas
        cumulative_qty = 0
        cs_shown = False
        for bid in demand_bids:
            if cumulative_qty >= eq_qty:
                break
            
            bid_start_qty = cumulative_qty
            bid_end_qty = min(bid['cumulative_quantity'], eq_qty)
            
            if bid_end_qty > bid_start_qty and bid['price'] > eq_price:
                fig.add_trace(go.Scatter(
                    x=[bid_start_qty, bid_end_qty, bid_end_qty, bid_start_qty, bid_start_qty],
                    y=[eq_price, eq_price, bid['price'], bid['price'], eq_price],
                    fill='toself',
                    fillcolor='rgba(0, 100, 255, 0.3)',
                    mode='none',
                    name='Consumer Surplus',
                    showlegend=not cs_shown,
                    line=dict(width=0)
                ))
                cs_shown = True
            
            cumulative_qty = bid['cumulative_quantity']
        
        # Add producer surplus areas
        cumulative_qty = 0
        ps_shown = False
        for bid in supply_bids:
            if cumulative_qty >= eq_qty:
                break
            
            bid_start_qty = cumulative_qty
            bid_end_qty = min(bid['cumulative_quantity'], eq_qty)
            
            if bid_end_qty > bid_start_qty and eq_price > bid['price']:
                fig.add_trace(go.Scatter(
                    x=[bid_start_qty, bid_end_qty, bid_end_qty, bid_start_qty, bid_start_qty],
                    y=[bid['price'], bid['price'], eq_price, eq_price, bid['price']],
                    fill='toself',
                    fillcolor='rgba(255, 100, 0, 0.3)',
                    mode='none',
                    name='Producer Surplus',
                    showlegend=not ps_shown,
                    line=dict(width=0)
                ))
                ps_shown = True
            
            cumulative_qty = bid['cumulative_quantity']
    
    # Add analysis points
    colors = ['purple', 'green', 'orange', 'brown', 'pink', 'cyan']
    for i, point in enumerate(analysis_points):
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=[point['quantity']],
            y=[point['price']],
            mode='markers',
            name=f'Analysis Point {i+1}',
            marker=dict(color=color, size=12, symbol='circle', line=dict(width=2, color='white')),
            hovertemplate=(
                f'<b>Analysis Point {i+1}</b><br>' +
                f'Quantity: {point["quantity"]:.1f} MWh<br>' +
                f'Price: ${point["price"]:.1f}/MWh<br>' +
                f'<br><b>Welfare Analysis:</b><br>' +
                f'Consumer Surplus: ${point.get("consumer_surplus", 0):.0f}<br>' +
                f'Producer Surplus: ${point.get("producer_surplus", 0):.0f}<br>' +
                f'Total Welfare: ${point.get("total_welfare", 0):.0f}<br>' +
                '<extra></extra>'
            )
        ))
        
        # Add reference lines for analysis points
        fig.add_hline(y=point['price'], line_dash="dot", line_color=color, opacity=0.3)
        fig.add_vline(x=point['quantity'], line_dash="dot", line_color=color, opacity=0.3)
    
    # Update layout
    fig.update_layout(
        title='Market Equilibrium Analysis',
        xaxis_title='Quantity (MWh)',
        yaxis_title='Price ($/MWh)',
        hovermode='closest',
        height=600,
        showlegend=True,
        xaxis=dict(range=[0, max_qty * 1.1]),
        yaxis=dict(range=[0, max(max(supply_y), max(demand_y)) * 1.1])
    )
    
    return fig

def create_supplier_model_plot(intercept, slope, clicked_points):
    """Create the supplier supply curve plot with areas"""
    # Generate supply curve points
    max_quantity = 100  # Set a reasonable max quantity for supply
    max_price = intercept + slope * max_quantity
    quantities = np.linspace(0, max_quantity * 1.1, 100)
    prices = intercept + slope * quantities
    
    # Create the main plot
    fig = go.Figure()
    
    # Add supply curve
    fig.add_trace(go.Scatter(
        x=quantities,
        y=prices,
        mode='lines',
        name='Supply Curve',
        line=dict(color='red', width=3),
        hovertemplate='Quantity: %{x:.2f}<br>Price: %{y:.2f}<extra></extra>'
    ))
    
    # Add clicked points and areas
    area_colors = [
        ('rgba(50, 205, 50, 0.4)', 'rgba(255, 99, 71, 0.4)'),     # Green revenue, Red cost
        ('rgba(0, 191, 255, 0.4)', 'rgba(255, 165, 0, 0.4)'),     # Deep sky blue revenue, Orange cost
        ('rgba(255, 20, 147, 0.4)', 'rgba(138, 43, 226, 0.4)'),   # Deep pink revenue, Blue violet cost
        ('rgba(32, 178, 170, 0.4)', 'rgba(255, 215, 0, 0.4)'),    # Light sea green revenue, Gold cost
        ('rgba(127, 255, 212, 0.4)', 'rgba(220, 20, 60, 0.4)'),   # Aquamarine revenue, Crimson cost
        ('rgba(255, 182, 193, 0.4)', 'rgba(75, 0, 130, 0.4)')     # Light pink revenue, Indigo cost
    ]
    marker_colors = ['red', 'orange', 'blueviolet', 'gold', 'crimson', 'indigo']
    
    for i, point in enumerate(clicked_points):
        quantity, price = point['quantity'], point['price']
        revenue_color, cost_color = area_colors[i % len(area_colors)]
        marker_color = marker_colors[i % len(marker_colors)]
        
        # Add horizontal and vertical reference lines for this point
        fig.add_hline(y=price, line_dash="dot", line_color="gray", opacity=0.3)
        fig.add_vline(x=quantity, line_dash="dot", line_color="gray", opacity=0.3)
        
        # Revenue area (rectangle: bottom-left is origin, top-right is (quantity, price))
        fig.add_trace(go.Scatter(
            x=[0, quantity, quantity, 0, 0],
            y=[0, 0, price, price, 0],
            fill='toself',
            fillcolor=revenue_color,
            mode='none',
            name=f'Revenue {i+1}',
            showlegend=True,
            line=dict(width=0),
            legendgroup=f'point{i+1}',
            legendgrouptitle_text=f"Point {i+1}" if i < 3 else None
        ))
        
        # Cost area (area under supply curve from 0 to quantity)
        supply_quantities = np.linspace(0, quantity, 50)
        supply_prices = intercept + slope * supply_quantities
        # Create proper polygon: start at origin, follow supply curve, then close at (quantity, 0)
        fig.add_trace(go.Scatter(
            x=np.concatenate([[0], supply_quantities, [quantity, 0]]),
            y=np.concatenate([[0], supply_prices, [0, 0]]),
            fill='toself',
            fillcolor=cost_color,
            mode='none',
            name=f'Cost {i+1}',
            showlegend=True,
            line=dict(width=0),
            legendgroup=f'point{i+1}',
        ))
        
        # Add the analysis point ON the supply curve
        fig.add_trace(go.Scatter(
            x=[quantity],
            y=[price],
            mode='markers',
            name=f'Analysis Point {i+1}',
            marker=dict(
                color=marker_color, 
                size=12, 
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            legendgroup=f'point{i+1}',
            hovertemplate=(
                f'<b>Point {i+1}</b><br>' +
                f'Quantity: {quantity:.1f} MWh<br>' +
                f'Price: ${price:.1f}/MWh<br>' +
                f'<br><b>Economic Analysis:</b><br>' +
                f'Revenue: ${point.get("revenue", 0):.0f}<br>' +
                f'Cost: ${point.get("cost", 0):.0f} ({point.get("cost_percentage", 0):.1f}% of Revenue)<br>' +
                f'Profit: ${point.get("profit", 0):.0f} ({point.get("profit_percentage", 0):.1f}% of Revenue)<br>' +
                '<extra></extra>'
            )
        ))
    
    # Update layout
    fig.update_layout(
        title='Supplier Supply Model',
        xaxis_title='Quantity (MWh)',
        yaxis_title='Price ($/MWh)',
        hovermode='closest',
        height=600,
        showlegend=True,
        xaxis=dict(range=[0, max_quantity * 1.1]),
        yaxis=dict(range=[0, max_price * 1.1])
    )
    
    return fig

def create_elasticity_plot(intercept, slope, elasticity_points):
    """Create the consumer demand curve plot with elasticity points"""
    # Generate demand curve points
    max_quantity = intercept / abs(slope)
    quantities = np.linspace(0, max_quantity * 1.1, 100)
    prices = intercept + slope * quantities
    
    # Create the main plot
    fig = go.Figure()
    
    # Add demand curve
    fig.add_trace(go.Scatter(
        x=quantities,
        y=prices,
        mode='lines',
        name='Demand Curve',
        line=dict(color='blue', width=3),
        hovertemplate='Quantity: %{x:.2f}<br>Price: %{y:.2f}<extra></extra>'
    ))
    
    # Add elasticity points
    colors = ['red', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta']
    
    for i, point in enumerate(elasticity_points):
        quantity, price = point['quantity'], point['price']
        color = colors[i % len(colors)]
        
        # Add point
        fig.add_trace(go.Scatter(
            x=[quantity],
            y=[price],
            mode='markers',
            name=f'Elasticity Point {i+1}',
            marker=dict(
                color=color, 
                size=12, 
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            hovertemplate=(
                f'<b>Elasticity Point {i+1}</b><br>' +
                f'Quantity: {quantity:.1f} MWh<br>' +
                f'Price: ${price:.1f}/MWh<br>' +
                f'<br><b>Analysis:</b><br>' +
                f'Slope: {point.get("slope", 0):.2f}<br>' +
                f'Price Elasticity: {point.get("elasticity", 0):.2f}<br>' +
                f'<br><b>Interpretation:</b><br>' +
                f'{point.get("interpretation", "")}<br>' +
                '<extra></extra>'
            )
        ))
    
    # Update layout
    fig.update_layout(
        title='Consumer Demand Model - Elasticity Analysis',
        xaxis_title='Quantity (MWh)',
        yaxis_title='Price ($/MWh)',
        hovermode='closest',
        height=600,
        showlegend=True,
        xaxis=dict(range=[0, max_quantity * 1.1]),
        yaxis=dict(range=[0, intercept * 1.1])
    )
    
    return fig

def create_supplier_elasticity_plot(intercept, slope, elasticity_points):
    """Create the supplier supply curve plot with elasticity points"""
    # Generate supply curve points
    max_quantity = 100  # Set a reasonable max quantity for supply
    max_price = intercept + slope * max_quantity
    quantities = np.linspace(0, max_quantity * 1.1, 100)
    prices = intercept + slope * quantities
    
    # Create the main plot
    fig = go.Figure()
    
    # Add supply curve
    fig.add_trace(go.Scatter(
        x=quantities,
        y=prices,
        mode='lines',
        name='Supply Curve',
        line=dict(color='red', width=3),
        hovertemplate='Quantity: %{x:.2f}<br>Price: %{y:.2f}<extra></extra>'
    ))
    
    # Add elasticity points
    colors = ['red', 'green', 'orange', 'purple', 'brown', 'pink', 'cyan', 'magenta']
    
    for i, point in enumerate(elasticity_points):
        quantity, price = point['quantity'], point['price']
        color = colors[i % len(colors)]
        
        # Add point
        fig.add_trace(go.Scatter(
            x=[quantity],
            y=[price],
            mode='markers',
            name=f'Elasticity Point {i+1}',
            marker=dict(
                color=color, 
                size=12, 
                symbol='circle',
                line=dict(width=2, color='white')
            ),
            showlegend=True,
            hovertemplate=(
                f'<b>Elasticity Point {i+1}</b><br>' +
                f'Quantity: {quantity:.1f} MWh<br>' +
                f'Price: ${price:.1f}/MWh<br>' +
                f'<br><b>Analysis:</b><br>' +
                f'Slope: {point.get("slope", 0):.2f}<br>' +
                f'Price Elasticity: {point.get("elasticity", 0):.2f}<br>' +
                f'<br><b>Interpretation:</b><br>' +
                f'{point.get("interpretation", "")}<br>' +
                '<extra></extra>'
            )
        ))
    
    # Update layout
    fig.update_layout(
        title='Supplier Supply Model - Elasticity Analysis',
        xaxis_title='Quantity (MWh)',
        yaxis_title='Price ($/MWh)',
        hovermode='closest',
        height=600,
        showlegend=True,
        xaxis=dict(range=[0, max_quantity * 1.1]),
        yaxis=dict(range=[0, max_price * 1.1])
    )
    
    return fig

def consumer_model_section():
    st.title("Consumer Model Analysis")
    st.markdown("Click on the demand curve to analyze consumer surplus, expenses, and net surplus at different price points.")
    
    # Create two columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Slope controller
        slope = st.slider(
            "Demand Curve Slope (negative)",
            min_value=-10.0,
            max_value=-0.1,
            value=-2.0,
            step=0.1,
            help="Controls the steepness of the demand curve"
        )
        
        # Intercept controller
        intercept = st.slider(
            "Price Intercept ($/MWh)",
            min_value=10.0,
            max_value=200.0,
            value=100.0,
            step=5.0,
            help="Maximum price when quantity is zero"
        )
        
        # Create and display the plot
        fig = create_consumer_model_plot(intercept, slope, st.session_state.click_data)
        
        # Handle click events
        clicked_point = st.plotly_chart(fig, use_container_width=True, key="consumer_plot")
        
        # Manual point addition (since Streamlit doesn't support click events easily)
        st.subheader("Add Analysis Point")
        col_q, col_p, col_add = st.columns([1, 1, 1])
        
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["By Price", "By Quantity"],
            horizontal=True,
            key="consumer_input_method"
        )
        
        if input_method == "By Price":
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_price = st.number_input(
                    "Market Price ($/MWh)",
                    min_value=0.1,
                    max_value=intercept-0.1,
                    value=50.0,
                    step=1.0,
                    help="Enter price - quantity will be calculated",
                    key="consumer_price"
                )
                # Unique key for "By Price"
                if st.button("Add Point", type="primary", key="consumer_add_price"):
                    calculated_quantity = (manual_price - intercept) / slope
                    max_quantity = intercept / abs(slope)
                    calculated_quantity = max(0, min(calculated_quantity, max_quantity))
                    final_price = manual_price
                    final_quantity = calculated_quantity

                    # Calculate areas
                    gross_surplus, expenses, net_surplus = calculate_areas(
                        intercept, slope, final_price, final_quantity
                    )

                    # Calculate percentages with respect to gross surplus
                    gs_pct = 100.0  # Gross surplus is always 100% of itself
                    exp_pct = (expenses / gross_surplus * 100) if gross_surplus > 0 else 0
                    net_pct = (net_surplus / gross_surplus * 100) if gross_surplus > 0 else 0

                    # Add to session state
                    st.session_state.click_data.append({
                        'quantity': final_quantity,
                        'price': final_price,
                        'gross_surplus': gross_surplus,
                        'expenses': expenses,
                        'net_surplus': net_surplus,
                        'gs_percentage': gs_pct,
                        'exp_percentage': exp_pct,
                        'net_percentage': net_pct
                    })
                    st.rerun()
            with col_calculated:
                calculated_quantity = (manual_price - intercept) / slope
                max_quantity = intercept / abs(slope)
                calculated_quantity = max(0, min(calculated_quantity, max_quantity))
                st.number_input(
                    "Calculated Quantity (MWh)",
                    value=calculated_quantity,
                    disabled=True,
                    help="Auto-calculated from demand curve"
                )
            final_price = manual_price
            final_quantity = calculated_quantity
            
        else:  # By Quantity
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_quantity = st.number_input(
                    "Quantity (MWh)",
                    min_value=0.0,
                    max_value=intercept/abs(slope),
                    value=20.0,
                    step=1.0,
                    help="Enter quantity - price will be calculated",
                    key="consumer_quantity"
                )
            with col_calculated:
                calculated_price = intercept + slope * manual_quantity
                calculated_price = max(0, calculated_price)
                st.number_input(
                    "Calculated Price ($/MWh)",
                    value=calculated_price,
                    disabled=True,
                    help="Auto-calculated from demand curve"
                )
            final_quantity = manual_quantity
            final_price = calculated_price
        
        # Only one "Add Point" button for "By Quantity"
        if input_method == "By Quantity":
            if st.button("Add Point", type="primary", key="consumer_add_quantity"):
                # Calculate areas
                gross_surplus, expenses, net_surplus = calculate_areas(
                    intercept, slope, final_price, final_quantity
                )
                
                # Calculate percentages with respect to gross surplus
                gs_pct = 100.0  # Gross surplus is always 100% of itself
                exp_pct = (expenses / gross_surplus * 100) if gross_surplus > 0 else 0
                net_pct = (net_surplus / gross_surplus * 100) if gross_surplus > 0 else 0
                
                # Add to session state
                st.session_state.click_data.append({
                    'quantity': final_quantity,
                    'price': final_price,
                    'gross_surplus': gross_surplus,
                    'expenses': expenses,
                    'net_surplus': net_surplus,
                    'gs_percentage': gs_pct,
                    'exp_percentage': exp_pct,
                    'net_percentage': net_pct
                })
                st.rerun()
    
    with col2:
        st.subheader("Analysis Results")
        
        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="consumer_clear_table"):
                st.session_state.click_data = []
                st.rerun()
        
        with col_clear2:
            if st.button("Clear Graph", type="secondary", key="consumer_clear_graph"):
                st.session_state.click_data = []
                st.rerun()
        
        # Display results table
        if st.session_state.click_data:
            # Create DataFrame
            df_data = []
            for i, point in enumerate(st.session_state.click_data):
                df_data.append({
                    'Point': i + 1,
                    'Quantity (MWh)': f"{point['quantity']:.1f}",
                    'Price ($/MWh)': f"{point['price']:.1f}",
                    'Gross Surplus ($)': f"{point['gross_surplus']:.0f}",
                    'Expenses ($)': f"{point['expenses']:.0f}",
                    'Net Surplus ($)': f"{point['net_surplus']:.0f}",
                    'Exp %': f"{point['exp_percentage']:.1f}%",
                    'Net %': f"{point['net_percentage']:.1f}%"
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Show tooltip-like information for the last point
            if st.session_state.click_data:
                last_point = st.session_state.click_data[-1]
                st.subheader("Latest Point Details")
                
                st.metric(
                    "Gross Surplus",
                    f"${last_point['gross_surplus']:.0f}",
                    "Total willingness to pay"
                )
                
                st.metric(
                    "Consumer Expenses",
                    f"${last_point['expenses']:.0f}",
                    f"{last_point['exp_percentage']:.1f}% of GS"
                )
                
                st.metric(
                    "Net Surplus",
                    f"${last_point['net_surplus']:.0f}",
                    f"{last_point['net_percentage']:.1f}% of GS"
                )
        else:
            st.info("Add points to the graph to see analysis results")

def supplier_model_section():
    st.title("Supplier Model Analysis")
    st.markdown("Click on the supply curve to analyze supplier revenue, cost, and profit at different price points.")
    
    # Create two columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Slope controller
        slope = st.slider(
            "Supply Curve Slope (positive)",
            min_value=0.1,
            max_value=10.0,
            value=2.0,
            step=0.1,
            help="Controls the steepness of the supply curve",
            key="supplier_slope"
        )
        
        # Intercept controller
        intercept = st.slider(
            "Price Intercept ($/MWh)",
            min_value=0.0,
            max_value=50.0,
            value=10.0,
            step=1.0,
            help="Minimum price when quantity is zero",
            key="supplier_intercept"
        )
        
        # Create and display the plot
        fig = create_supplier_model_plot(intercept, slope, st.session_state.supplier_click_data)
        
        # Handle click events
        clicked_point = st.plotly_chart(fig, use_container_width=True, key="supplier_plot")
        
        # Manual point addition
        st.subheader("Add Analysis Point")
        
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["By Price", "By Quantity"],
            horizontal=True,
            key="supplier_input_method"
        )
        
        if input_method == "By Price":
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_price = st.number_input(
                    "Market Price ($/MWh)",
                    min_value=intercept + 0.1,
                    max_value=200.0,
                    value=50.0,
                    step=1.0,
                    help="Enter price - quantity will be calculated",
                    key="supplier_price"
                )
                if st.button("Add Point", type="primary", key="supplier_add_price"):
                    calculated_quantity = (manual_price - intercept) / slope
                    calculated_quantity = max(0, calculated_quantity)
                    final_price = manual_price
                    final_quantity = calculated_quantity

                    # Calculate areas
                    revenue, cost, profit = calculate_supplier_areas(
                        intercept, slope, final_price, final_quantity
                    )

                    # Calculate percentages with respect to revenue
                    cost_pct = (cost / revenue * 100) if revenue > 0 else 0
                    profit_pct = (profit / revenue * 100) if revenue > 0 else 0

                    # Add to session state
                    st.session_state.supplier_click_data.append({
                        'quantity': final_quantity,
                        'price': final_price,
                        'revenue': revenue,
                        'cost': cost,
                        'profit': profit,
                        'cost_percentage': cost_pct,
                        'profit_percentage': profit_pct
                    })
                    st.rerun()
            with col_calculated:
                calculated_quantity = (manual_price - intercept) / slope
                calculated_quantity = max(0, calculated_quantity)
                st.number_input(
                    "Calculated Quantity (MWh)",
                    value=calculated_quantity,
                    disabled=True,
                    help="Auto-calculated from supply curve"
                )
            
        else:  # By Quantity
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_quantity = st.number_input(
                    "Quantity (MWh)",
                    min_value=0.1,
                    max_value=100.0,
                    value=20.0,
                    step=1.0,
                    help="Enter quantity - price will be calculated",
                    key="supplier_quantity"
                )
            with col_calculated:
                calculated_price = intercept + slope * manual_quantity
                st.number_input(
                    "Calculated Price ($/MWh)",
                    value=calculated_price,
                    disabled=True,
                    help="Auto-calculated from supply curve"
                )
            
            if st.button("Add Point", type="primary", key="supplier_add_quantity"):
                final_quantity = manual_quantity
                final_price = calculated_price
                
                # Calculate areas
                revenue, cost, profit = calculate_supplier_areas(
                    intercept, slope, final_price, final_quantity
                )
                
                # Calculate percentages with respect to revenue
                cost_pct = (cost / revenue * 100) if revenue > 0 else 0
                profit_pct = (profit / revenue * 100) if revenue > 0 else 0
                
                # Add to session state
                st.session_state.supplier_click_data.append({
                    'quantity': final_quantity,
                    'price': final_price,
                    'revenue': revenue,
                    'cost': cost,
                    'profit': profit,
                    'cost_percentage': cost_pct,
                    'profit_percentage': profit_pct
                })
                st.rerun()
    
    with col2:
        st.subheader("Analysis Results")
        
        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="supplier_clear_table"):
                st.session_state.supplier_click_data = []
                st.rerun()
        
        with col_clear2:
            if st.button("Clear Graph", type="secondary", key="supplier_clear_graph"):
                st.session_state.supplier_click_data = []
                st.rerun()
        
        # Display results table
        if st.session_state.supplier_click_data:
            # Create DataFrame
            df_data = []
            for i, point in enumerate(st.session_state.supplier_click_data):
                df_data.append({
                    'Point': i + 1,
                    'Quantity (MWh)': f"{point['quantity']:.1f}",
                    'Price ($/MWh)': f"{point['price']:.1f}",
                    'Revenue ($)': f"{point['revenue']:.0f}",
                    'Cost ($)': f"{point['cost']:.0f}",
                    'Profit ($)': f"{point['profit']:.0f}",
                    'Cost %': f"{point['cost_percentage']:.1f}%",
                    'Profit %': f"{point['profit_percentage']:.1f}%"
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Show tooltip-like information for the last point
            if st.session_state.supplier_click_data:
                last_point = st.session_state.supplier_click_data[-1]
                st.subheader("Latest Point Details")
                
                st.metric(
                    "Revenue",
                    f"${last_point['revenue']:.0f}",
                    "Total income from sales"
                )
                
                st.metric(
                    "Cost",
                    f"${last_point['cost']:.0f}",
                    f"{last_point['cost_percentage']:.1f}% of Revenue"
                )
                
                st.metric(
                    "Profit (Producer Surplus)",
                    f"${last_point['profit']:.0f}",
                    f"{last_point['profit_percentage']:.1f}% of Revenue"
                )
        else:
            st.info("Add points to the graph to see analysis results")

def consumer_elasticity_section():
    st.title("Consumer Elasticity Analysis")
    st.markdown("Analyze price elasticity of demand at different points on the consumer demand curve and understand how it differs from the constant slope.")
    
    # Create two columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Slope controller
        slope = st.slider(
            "Demand Curve Slope (negative)",
            min_value=-10.0,
            max_value=-0.1,
            value=-2.0,
            step=0.1,
            help="Controls the steepness of the demand curve",
            key="elasticity_slope"
        )
        
        # Intercept controller
        intercept = st.slider(
            "Price Intercept ($/MWh)",
            min_value=10.0,
            max_value=200.0,
            value=100.0,
            step=5.0,
            help="Maximum price when quantity is zero",
            key="elasticity_intercept"
        )
        
        # Create and display the plot
        fig = create_elasticity_plot(intercept, slope, st.session_state.elasticity_data)
        
        # Handle click events
        clicked_point = st.plotly_chart(fig, use_container_width=True, key="elasticity_plot")
        
        # Manual point addition
        st.subheader("Add Elasticity Analysis Point")
        col_q, col_p, col_add = st.columns([1, 1, 1])
        
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["By Price", "By Quantity"],
            horizontal=True,
            key="elasticity_input_method"
        )
        
        if input_method == "By Price":
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_price = st.number_input(
                    "Market Price ($/MWh)",
                    min_value=0.1,
                    max_value=intercept-0.1,
                    value=50.0,
                    step=1.0,
                    help="Enter price - quantity will be calculated",
                    key="elasticity_price"
                )
            with col_calculated:
                calculated_quantity = (manual_price - intercept) / slope
                max_quantity = intercept / abs(slope)
                calculated_quantity = max(0.1, min(calculated_quantity, max_quantity))
                st.number_input(
                    "Calculated Quantity (MWh)",
                    value=calculated_quantity,
                    disabled=True,
                    help="Auto-calculated from demand curve"
                )
            final_price = manual_price
            final_quantity = calculated_quantity
            
        else:  # By Quantity
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_quantity = st.number_input(
                    "Quantity (MWh)",
                    min_value=0.1,
                    max_value=intercept/abs(slope),
                    value=20.0,
                    step=1.0,
                    help="Enter quantity - price will be calculated",
                    key="elasticity_quantity"
                )
            with col_calculated:
                calculated_price = intercept + slope * manual_quantity
                calculated_price = max(0.1, calculated_price)
                st.number_input(
                    "Calculated Price ($/MWh)",
                    value=calculated_price,
                    disabled=True,
                    help="Auto-calculated from demand curve"
                )
            final_quantity = manual_quantity
            final_price = calculated_price
        
        col_add_button = st.columns([1])[0]
        with col_add_button:
            if st.button("Add Point", type="primary", key="elasticity_add"):
                
                # Calculate elasticity
                elasticity = calculate_elasticity(intercept, slope, final_quantity, final_price)
                
                # Interpretation of elasticity
                if abs(elasticity) > 1:
                    interpretation = "Elastic (|ε| > 1): Responsive to price changes"
                elif abs(elasticity) == 1:
                    interpretation = "Unit Elastic (|ε| = 1): Proportional response"
                else:
                    interpretation = "Inelastic (|ε| < 1): Less responsive to price changes"
                
                # Add to session state
                st.session_state.elasticity_data.append({
                    'quantity': final_quantity,
                    'price': final_price,
                    'slope': slope,
                    'elasticity': elasticity,
                    'interpretation': interpretation
                })
                st.rerun()
    
    with col2:
        st.subheader("Elasticity Results")
        
        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="elasticity_clear_table"):
                st.session_state.elasticity_data = []
                st.rerun()
        
        with col_clear2:
            if st.button("Clear Graph", type="secondary", key="elasticity_clear_graph"):
                st.session_state.elasticity_data = []
                st.rerun()
        
        # Display results table
        if st.session_state.elasticity_data:
            # Create DataFrame
            df_data = []
            for i, point in enumerate(st.session_state.elasticity_data):
                df_data.append({
                    'Point': i + 1,
                    'Quantity (MWh)': f"{point['quantity']:.1f}",
                    'Price ($/MWh)': f"{point['price']:.1f}",
                    'Slope': f"{point['slope']:.2f}",
                    'Elasticity': f"{point['elasticity']:.2f}",
                    'Type': point['interpretation'].split(':')[0]
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Show details for the last point
            if st.session_state.elasticity_data:
                last_point = st.session_state.elasticity_data[-1]
                st.subheader("Latest Point Details")
                
                st.metric(
                    "Slope",
                    f"{last_point['slope']:.2f}",
                    "Constant along demand curve"
                )
                
                st.metric(
                    "Price Elasticity",
                    f"{last_point['elasticity']:.2f}",
                    "Varies along demand curve"
                )
                
                st.info(f"**{last_point['interpretation']}**")
        else:
            st.info("Add points to analyze price elasticity")

def market_equilibrium_section():
    st.title("Market Equilibrium Analysis")
    st.markdown("Generate supply and demand bid stacks to analyze market clearing price, quantity, and global welfare.")
    
    # Create two columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Bid generation controls
        st.subheader("Generate Market Bids")
        
        col_supply, col_demand = st.columns(2)
        
        with col_supply:
            st.markdown("**Supply Bids**")
            supply_num_bids = st.slider("Number of Supply Bids", 5, 20, 10, key="supply_num_bids")
            supply_max_qty = st.slider("Max Bid Quantity", 5, 20, 10, key="supply_max_qty")
            supply_min_price = st.slider("Min Price", 5, 30, 10, key="supply_min_price")
            supply_max_price = st.slider("Max Price", 40, 120, 80, key="supply_max_price")
            
            if st.button("Generate Supply Bids", type="primary", key="gen_supply"):
                st.session_state.supply_bids = generate_supply_bids(
                    supply_num_bids, supply_max_qty, supply_min_price, supply_max_price
                )
                st.rerun()
        
        with col_demand:
            st.markdown("**Demand Bids**")
            demand_num_bids = st.slider("Number of Demand Bids", 5, 20, 10, key="demand_num_bids")
            demand_max_qty = st.slider("Max Bid Quantity", 5, 20, 10, key="demand_max_qty")
            demand_min_price = st.slider("Min Price", 20, 50, 30, key="demand_min_price")
            demand_max_price = st.slider("Max Price", 60, 150, 100, key="demand_max_price")
            
            if st.button("Generate Demand Bids", type="primary", key="gen_demand"):
                st.session_state.demand_bids = generate_demand_bids(
                    demand_num_bids, demand_max_qty, demand_min_price, demand_max_price
                )
                st.rerun()
        
        # Generate both at once
        col_gen_both = st.columns([1])[0]
        with col_gen_both:
            if st.button("Generate Both Bid Stacks", type="primary", key="gen_both"):
                st.session_state.supply_bids = generate_supply_bids(
                    supply_num_bids, supply_max_qty, supply_min_price, supply_max_price
                )
                st.session_state.demand_bids = generate_demand_bids(
                    demand_num_bids, demand_max_qty, demand_min_price, demand_max_price
                )
                st.rerun()
        
        # Market equilibrium plot
        fig = create_market_equilibrium_plot(
            st.session_state.supply_bids, 
            st.session_state.demand_bids, 
            st.session_state.market_analysis_data
        )
        st.plotly_chart(fig, use_container_width=True, key="market_plot")
        
        # Show equilibrium information
        if st.session_state.supply_bids and st.session_state.demand_bids:
            eq_qty, eq_price = find_market_equilibrium(st.session_state.supply_bids, st.session_state.demand_bids)
            if eq_qty > 0:
                cs, ps, total_welfare = calculate_market_welfare(
                    st.session_state.supply_bids, st.session_state.demand_bids, eq_price, eq_qty
                )
                
                col_eq1, col_eq2, col_eq3 = st.columns(3)
                with col_eq1:
                    st.metric("Market Clearing Price", f"${eq_price:.1f}/MWh")
                with col_eq2:
                    st.metric("Market Clearing Quantity", f"{eq_qty:.1f} MWh")
                with col_eq3:
                    st.metric("Total Welfare", f"${total_welfare:.0f}")
        
        # Manual welfare analysis
        st.subheader("Welfare Analysis at Different Price Points")
        
        input_method = st.radio(
            "Choose input method:",
            ["By Price", "By Quantity"],
            horizontal=True,
            key="market_input_method"
        )
        
        if input_method == "By Price":
            analysis_price = st.number_input(
                "Analysis Price ($/MWh)",
                min_value=0.1,
                max_value=200.0,
                value=50.0,
                step=1.0,
                key="market_analysis_price"
            )
            
            if st.button("Add Analysis Point", type="primary", key="market_add_price"):
                if st.session_state.supply_bids and st.session_state.demand_bids:
                    # Find quantities willing to be supplied and demanded at this price
                    supply_qty = 0
                    for bid in st.session_state.supply_bids:
                        if bid['price'] <= analysis_price:
                            supply_qty = bid['cumulative_quantity']
                        else:
                            break
                    
                    demand_qty = 0
                    for bid in st.session_state.demand_bids:
                        if bid['price'] >= analysis_price:
                            demand_qty = bid['cumulative_quantity']
                        else:
                            break
                    
                    # The actual traded quantity is the minimum of supply and demand
                    analysis_qty = min(supply_qty, demand_qty)
                    
                    # Calculate welfare at this price and quantity
                    cs, ps, total_welfare = calculate_market_welfare(
                        st.session_state.supply_bids, st.session_state.demand_bids, 
                        analysis_price, analysis_qty
                    )
                    
                    st.session_state.market_analysis_data.append({
                        'price': analysis_price,
                        'quantity': analysis_qty,
                        'consumer_surplus': cs,
                        'producer_surplus': ps,
                        'total_welfare': total_welfare
                    })
                    st.rerun()
        
        else:  # By Quantity
            max_possible_qty = 0
            if st.session_state.supply_bids and st.session_state.demand_bids:
                max_possible_qty = min(
                    st.session_state.supply_bids[-1]['cumulative_quantity'],
                    st.session_state.demand_bids[-1]['cumulative_quantity']
                )
            
            analysis_qty = st.number_input(
                "Analysis Quantity (MWh)",
                min_value=0.1,
                max_value=max(max_possible_qty, 100.0),
                value=min(20.0, max_possible_qty) if max_possible_qty > 0 else 20.0,
                step=1.0,
                key="market_analysis_quantity"
            )
            
            if st.button("Add Analysis Point", type="primary", key="market_add_qty"):
                if st.session_state.supply_bids and st.session_state.demand_bids:
                    # Find the marginal supply price for this quantity
                    supply_price = float('inf')
                    for bid in st.session_state.supply_bids:
                        if analysis_qty <= bid['cumulative_quantity']:
                            supply_price = bid['price']
                            break
                    
                    # Find the marginal demand price for this quantity  
                    demand_price = 0
                    for bid in st.session_state.demand_bids:
                        if analysis_qty <= bid['cumulative_quantity']:
                            demand_price = bid['price']
                            break
                    
                    # For welfare analysis, we need a market price
                    # Use the supply price (marginal cost) as the analysis price
                    analysis_price = supply_price if supply_price != float('inf') else demand_price
                    
                    # Calculate welfare at this price and quantity
                    cs, ps, total_welfare = calculate_market_welfare(
                        st.session_state.supply_bids, st.session_state.demand_bids, 
                        analysis_price, analysis_qty
                    )
                    
                    st.session_state.market_analysis_data.append({
                        'price': analysis_price,
                        'quantity': analysis_qty,
                        'consumer_surplus': cs,
                        'producer_surplus': ps,
                        'total_welfare': total_welfare
                    })
                    st.rerun()
    
    with col2:
        st.subheader("Market Analysis")
        
        # Show bid tables
        if st.session_state.supply_bids:
            st.markdown("**Supply Bids**")
            supply_df = pd.DataFrame([
                {
                    'Bid': bid['bid_id'],
                    'Qty': f"{bid['quantity']:.1f}",
                    'Price': f"${bid['price']:.1f}",
                    'Cum Qty': f"{bid['cumulative_quantity']:.1f}"
                }
                for bid in st.session_state.supply_bids[:5]  # Show first 5
            ])
            st.dataframe(supply_df, use_container_width=True)
            if len(st.session_state.supply_bids) > 5:
                st.caption(f"... and {len(st.session_state.supply_bids) - 5} more")
        
        if st.session_state.demand_bids:
            st.markdown("**Demand Bids**")
            demand_df = pd.DataFrame([
                {
                    'Bid': bid['bid_id'],
                    'Qty': f"{bid['quantity']:.1f}",
                    'Price': f"${bid['price']:.1f}",
                    'Cum Qty': f"{bid['cumulative_quantity']:.1f}"
                }
                for bid in st.session_state.demand_bids[:5]  # Show first 5
            ])
            st.dataframe(demand_df, use_container_width=True)
            if len(st.session_state.demand_bids) > 5:
                st.caption(f"... and {len(st.session_state.demand_bids) - 5} more")
        
        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Analysis", type="secondary", key="market_clear_analysis"):
                st.session_state.market_analysis_data = []
                st.rerun()
        
        with col_clear2:
            if st.button("Clear Bids", type="secondary", key="market_clear_bids"):
                st.session_state.supply_bids = []
                st.session_state.demand_bids = []
                st.session_state.market_analysis_data = []
                st.rerun()
        
        # Analysis results
        if st.session_state.market_analysis_data:
            st.subheader("Welfare Analysis Results")
            
            # Create DataFrame
            analysis_df = pd.DataFrame([
                {
                    'Point': i + 1,
                    'Price': f"${point['price']:.1f}",
                    'Quantity': f"{point['quantity']:.1f}",
                    'CS': f"${point['consumer_surplus']:.0f}",
                    'PS': f"${point['producer_surplus']:.0f}",
                    'Total': f"${point['total_welfare']:.0f}"
                }
                for i, point in enumerate(st.session_state.market_analysis_data)
            ])
            
            st.dataframe(analysis_df, use_container_width=True)
            
            # Show details for last point
            if st.session_state.market_analysis_data:
                last_point = st.session_state.market_analysis_data[-1]
                st.subheader("Latest Analysis")
                
                # Get equilibrium values for comparison
                eq_qty, eq_price = find_market_equilibrium(st.session_state.supply_bids, st.session_state.demand_bids)
                eq_cs, eq_ps, eq_total_welfare = calculate_market_welfare(
                    st.session_state.supply_bids, st.session_state.demand_bids, eq_price, eq_qty
                ) if eq_qty > 0 and eq_price > 0 else (0, 0, 0)
                
                # Calculate changes from equilibrium
                cs_change = last_point['consumer_surplus'] - eq_cs
                ps_change = last_point['producer_surplus'] - eq_ps
                total_change = last_point['total_welfare'] - eq_total_welfare
                
                # Calculate percentage changes
                cs_pct = (cs_change / eq_cs * 100) if eq_cs > 0 else 0
                ps_pct = (ps_change / eq_ps * 100) if eq_ps > 0 else 0
                total_pct = (total_change / eq_total_welfare * 100) if eq_total_welfare > 0 else 0
                
                # Format delta strings, handling zero case
                cs_delta = f"{cs_change:+.0f} ({cs_pct:+.1f}% vs equilibrium)" if abs(cs_change) >= 0.5 else None
                ps_delta = f"{ps_change:+.0f} ({ps_pct:+.1f}% vs equilibrium)" if abs(ps_change) >= 0.5 else None
                total_delta = f"{total_change:+.0f} ({total_pct:+.1f}% vs equilibrium)" if abs(total_change) >= 0.5 else None
                
                st.metric(
                    "Consumer Surplus",
                    f"${last_point['consumer_surplus']:.0f}",
                    cs_delta
                )
                
                st.metric(
                    "Producer Surplus",
                    f"${last_point['producer_surplus']:.0f}",
                    ps_delta
                )
                
                st.metric(
                    "Total Welfare",
                    f"${last_point['total_welfare']:.0f}",
                    total_delta
                )
                
                # Show equilibrium comparison info
                if eq_total_welfare > 0:
                    st.info(f"**Equilibrium Reference:** Price: ${eq_price:.1f}, Qty: {eq_qty:.1f}, Total Welfare: ${eq_total_welfare:.0f}")
        else:
            st.info("Generate bids and add analysis points to see welfare calculations")

def supplier_elasticity_section():
    st.title("Supplier Elasticity Analysis")
    st.markdown("Analyze price elasticity of supply at different points on the supplier supply curve and understand how it differs from the constant slope.")
    
    # Create two columns
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Slope controller
        slope = st.slider(
            "Supply Curve Slope (positive)",
            min_value=0.1,
            max_value=10.0,
            value=2.0,
            step=0.1,
            help="Controls the steepness of the supply curve",
            key="supplier_elasticity_slope"
        )
        
        # Intercept controller
        intercept = st.slider(
            "Price Intercept ($/MWh)",
            min_value=0.0,
            max_value=50.0,
            value=10.0,
            step=1.0,
            help="Minimum price when quantity is zero",
            key="supplier_elasticity_intercept"
        )
        
        # Create and display the plot
        fig = create_supplier_elasticity_plot(intercept, slope, st.session_state.supplier_elasticity_data)
        
        # Handle click events
        clicked_point = st.plotly_chart(fig, use_container_width=True, key="supplier_elasticity_plot")
        
        # Manual point addition
        st.subheader("Add Elasticity Analysis Point")
        
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["By Price", "By Quantity"],
            horizontal=True,
            key="supplier_elasticity_input_method"
        )
        
        if input_method == "By Price":
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_price = st.number_input(
                    "Market Price ($/MWh)",
                    min_value=intercept + 0.1,
                    max_value=200.0,
                    value=50.0,
                    step=1.0,
                    help="Enter price - quantity will be calculated",
                    key="supplier_elasticity_price"
                )
            with col_calculated:
                calculated_quantity = (manual_price - intercept) / slope
                calculated_quantity = max(0.1, calculated_quantity)
                st.number_input(
                    "Calculated Quantity (MWh)",
                    value=calculated_quantity,
                    disabled=True,
                    help="Auto-calculated from supply curve"
                )
            final_price = manual_price
            final_quantity = calculated_quantity
            
        else:  # By Quantity
            col_input, col_calculated = st.columns(2)
            with col_input:
                manual_quantity = st.number_input(
                    "Quantity (MWh)",
                    min_value=0.1,
                    max_value=100.0,
                    value=20.0,
                    step=1.0,
                    help="Enter quantity - price will be calculated",
                    key="supplier_elasticity_quantity"
                )
            with col_calculated:
                calculated_price = intercept + slope * manual_quantity
                st.number_input(
                    "Calculated Price ($/MWh)",
                    value=calculated_price,
                    disabled=True,
                    help="Auto-calculated from supply curve"
                )
            final_quantity = manual_quantity
            final_price = calculated_price
        
        if st.button("Add Point", type="primary", key="supplier_elasticity_add"):
            # Calculate elasticity
            elasticity = calculate_elasticity(intercept, slope, final_quantity, final_price)
            
            # Interpretation of elasticity for supply
            if abs(elasticity) > 1:
                interpretation = "Elastic (|ε| > 1): Responsive to price changes"
            elif abs(elasticity) == 1:
                interpretation = "Unit Elastic (|ε| = 1): Proportional response"
            else:
                interpretation = "Inelastic (|ε| < 1): Less responsive to price changes"
            
            # Add to session state
            st.session_state.supplier_elasticity_data.append({
                'quantity': final_quantity,
                'price': final_price,
                'slope': slope,
                'elasticity': elasticity,
                'interpretation': interpretation
            })
            st.rerun()
    
    with col2:
        st.subheader("Elasticity Results")
        
        # Clear buttons
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("Clear Table", type="secondary", key="supplier_elasticity_clear_table"):
                st.session_state.supplier_elasticity_data = []
                st.rerun()
        
        with col_clear2:
            if st.button("Clear Graph", type="secondary", key="supplier_elasticity_clear_graph"):
                st.session_state.supplier_elasticity_data = []
                st.rerun()
        
        # Display results table
        if st.session_state.supplier_elasticity_data:
            # Create DataFrame
            df_data = []
            for i, point in enumerate(st.session_state.supplier_elasticity_data):
                df_data.append({
                    'Point': i + 1,
                    'Quantity (MWh)': f"{point['quantity']:.1f}",
                    'Price ($/MWh)': f"{point['price']:.1f}",
                    'Slope': f"{point['slope']:.2f}",
                    'Elasticity': f"{point['elasticity']:.2f}",
                    'Type': point['interpretation'].split(':')[0]
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Show details for the last point
            if st.session_state.supplier_elasticity_data:
                last_point = st.session_state.supplier_elasticity_data[-1]
                st.subheader("Latest Point Details")
                
                st.metric(
                    "Slope",
                    f"{last_point['slope']:.2f}",
                    "Constant along supply curve"
                )
                
                st.metric(
                    "Price Elasticity",
                    f"{last_point['elasticity']:.2f}",
                    "Varies along supply curve"
                )
                
                st.info(f"**{last_point['interpretation']}**")
        else:
            st.info("Add points to analyze price elasticity")

# Run the appropriate section first
if page == "Consumer Model":
    consumer_model_section()
elif page == "Consumer Elasticity":
    consumer_elasticity_section()
elif page == "Supplier Model":
    supplier_model_section()
elif page == "Supplier Elasticity":
    supplier_elasticity_section()
elif page == "Market Equilibrium":
    market_equilibrium_section()

def main():
    # Educational content
    with st.expander("📚 Educational Content"):
        if page == "Consumer Model":
            st.markdown("""
            ### Consumer Surplus Concepts
            
            **Gross Surplus**: The total utility/value consumers derive from consuming a quantity of electricity. 
            Graphically, it's the entire area under the demand curve from 0 to the quantity consumed.
            
            **Consumer Expenses**: The total amount consumers actually pay for the quantity consumed (Price × Quantity).
            This is the rectangular area below the price line.
            
            **Net Surplus**: The actual consumer surplus - the benefit consumers receive beyond what they pay. 
            This equals Gross Surplus minus Expenses, and represents the triangular area between the demand curve and the price line.
            
            ### Economic Interpretation
            - **Gross Surplus** = Total willingness to pay
            - **Expenses** = Actual payment made  
            - **Net Surplus** = Consumer benefit (always positive for rational consumers)
            - All percentages are calculated relative to the Gross Surplus
            
            ### How to Use This Tool
            1. Adjust the slope to see how demand elasticity affects consumer surplus
            2. Use the quantity and price inputs to add analysis points
            3. Observe how different price points affect the areas and percentages
            4. Compare multiple scenarios using the results table
            """)
        
        elif page == "Consumer Elasticity":
            st.markdown("""
            ### Price Elasticity of Demand
            
            **Price Elasticity of Demand**: Measures how responsive quantity demanded is to changes in price.
            
            **Formula**: ε = (% change in quantity demanded) / (% change in price) = (dQ/dP) × (P/Q)
            
            **Key Differences**:
            - **Slope**: Constant along the entire demand curve (dP/dQ)
            - **Elasticity**: Varies at different points along the same demand curve
            
            ### Elasticity Categories
            - **Elastic (|ε| > 1)**: Quantity is very responsive to price changes
            - **Unit Elastic (|ε| = 1)**: Proportional response to price changes  
            - **Inelastic (|ε| < 1)**: Quantity is less responsive to price changes
            
            ### Economic Insights
            - Higher prices → Higher elasticity (more elastic)
            - Lower prices → Lower elasticity (more inelastic)
            - Same slope, different elasticity at each point
            - Important for pricing strategies in electricity markets
            
            ### How to Use This Tool
            1. Adjust slope and intercept to see different demand curves
            2. Add points at different price levels
            3. Compare slope (constant) vs elasticity (varying)
            4. Observe how elasticity changes along the curve
            """)
        
        elif page == "Supplier Model":
            st.markdown("""
            ### Producer Surplus Concepts
            
            **Revenue**: The total income suppliers receive from selling electricity (Price × Quantity).
            Graphically, it's the rectangular area: price line × quantity.
            
            **Cost**: The total cost of producing the quantity supplied.
            This is the area under the supply curve from 0 to the quantity produced.
            
            **Profit (Producer Surplus)**: The benefit suppliers receive beyond their costs.
            This equals Revenue minus Cost, and represents the area between the supply curve and the price line.
            
            ### Economic Interpretation
            - **Revenue** = Total income from sales (P × Q)
            - **Cost** = Total production cost (area under supply curve)
            - **Profit** = Producer surplus (Revenue - Cost)
            - All percentages are calculated relative to the Revenue
            
            ### How to Use This Tool
            1. Adjust the slope to see how supply elasticity affects producer surplus
            2. Use the quantity and price inputs to add analysis points
            3. Observe how different price points affect revenue, cost, and profit
            4. Compare multiple scenarios using the results table
            """)
        
        elif page == "Supplier Elasticity":
            st.markdown("""
            ### Price Elasticity of Supply
            
            **Price Elasticity of Supply**: Measures how responsive quantity supplied is to changes in price.
            
            **Formula**: ε = (% change in quantity supplied) / (% change in price) = (dQ/dP) × (P/Q)
            
            **Key Differences**:
            - **Slope**: Constant along the entire supply curve (dP/dQ)
            - **Elasticity**: Varies at different points along the same supply curve
            
            ### Elasticity Categories
            - **Elastic (|ε| > 1)**: Quantity is very responsive to price changes
            - **Unit Elastic (|ε| = 1)**: Proportional response to price changes  
            - **Inelastic (|ε| < 1)**: Quantity is less responsive to price changes
            
            ### Economic Insights for Supply
            - Higher prices → Lower elasticity (more inelastic)
            - Lower prices → Higher elasticity (more elastic)
            - Same slope, different elasticity at each point
            - Important for understanding supplier behavior in electricity markets
            
            ### How to Use This Tool
            1. Adjust slope and intercept to see different supply curves
            2. Add points at different price levels
            3. Compare slope (constant) vs elasticity (varying)
            4. Observe how supply elasticity changes along the curve
            """)
        
        elif page == "Market Equilibrium":
            st.markdown("""
            ### Market Equilibrium Concepts
            
            **Market Equilibrium**: The point where supply and demand curves intersect, determining the market clearing price and quantity.
            
            **Bid Stacks**: Representation of market participants' offers:
            - **Supply Stack**: Monotonically increasing prices (generators willing to sell)
            - **Demand Stack**: Monotonically decreasing prices (consumers willing to buy)
            
            ### Key Economic Measures
            - **Market Clearing Price**: Price at which supply equals demand
            - **Market Clearing Quantity**: Quantity traded at equilibrium
            - **Consumer Surplus**: Benefit to consumers (area above price, below demand)
            - **Producer Surplus**: Benefit to suppliers (area below price, above supply)
            - **Total Welfare**: Sum of consumer and producer surplus
            
            ### Market Efficiency
            - **Pareto Efficiency**: Market equilibrium maximizes total welfare
            - **Deadweight Loss**: Reduction in welfare from non-equilibrium prices
            - **Global Welfare**: Total economic benefit to society
            
            ### Real-World Application
            - Models electricity spot markets and auctions
            - Shows how bid stacks determine market prices
            - Demonstrates welfare implications of different market outcomes
            - Helps understand market power and efficiency
            
            ### How to Use This Tool
            1. Generate random supply and demand bid stacks
            2. Observe the market equilibrium point automatically calculated
            3. Analyze welfare at different price points
            4. Compare total welfare under different scenarios
            5. Understand the relationship between market price and global welfare
            """)

# Call main function to show educational content
main()