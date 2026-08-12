"""Consumer Model.

Extracted from week2_consumer_supplier.py (consumer_model_section) on 2026-08-12."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

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

    with st.expander("📚 Educational Content"):
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
