"""Supplier Model.

Extracted from week2_consumer_supplier.py (supplier_model_section) on 2026-08-12."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

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

    with st.expander("📚 Educational Content"):
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
