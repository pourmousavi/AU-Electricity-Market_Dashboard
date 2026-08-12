"""Market Equilibrium.

Extracted from week2_consumer_supplier.py (market_equilibrium_section) on 2026-08-12."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

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
    
    # Extend demand curve to x-axis: drop vertically at the last bid, then run
    # flat. Appending only the far point drew one diagonal from the last bid's
    # price down to zero, which is the one segment of the stack that did not
    # look like a step.
    demand_x.append(demand_bids[-1]['cumulative_quantity'])
    demand_y.append(0)
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

def render() -> None:
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

    with st.expander("📚 Educational Content"):
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
