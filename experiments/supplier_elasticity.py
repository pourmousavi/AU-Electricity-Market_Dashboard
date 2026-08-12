"""Supplier Elasticity.

Extracted from week2_consumer_supplier.py (supplier_elasticity_section) on 2026-08-12."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

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

    with st.expander("📚 Educational Content"):
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
