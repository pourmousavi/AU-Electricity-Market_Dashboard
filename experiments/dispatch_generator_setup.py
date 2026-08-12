"""Dispatch generator setup.

Extracted from week7_ed_viu.py (render_generator_table, plus the rest of tab 1
at lines 1634-1674) on 2026-08-12. The CSS, session state, sidebar and footer
shared with the other dispatch experiments live in
experiments/_kit/dispatch.py.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import cvxpy as cp
from scipy.optimize import minimize
import warnings
warnings.filterwarnings('ignore')

from experiments._kit import dispatch

STATE_GROUP = "dispatch"


def render_generator_table():
    """Render editable generator parameters table"""
    st.markdown("## 🏭 Generator Parameters")
    
    # Convert generator data to DataFrame for editing
    df_generators = pd.DataFrame(st.session_state.generators)
    
    # Create the editable data editor
    edited_df = st.data_editor(
        df_generators,
        column_config={
            "name": st.column_config.TextColumn("Generator Name", width="medium"),
            "type": st.column_config.SelectboxColumn(
                "Type", 
                options=["Coal", "Gas", "Hydro", "Nuclear", "Wind", "Solar"],
                width="small"
            ),
            "pmin": st.column_config.NumberColumn("Pmin (MW)", min_value=0, max_value=500, step=5, width="small"),
            "pmax": st.column_config.NumberColumn("Pmax (MW)", min_value=10, max_value=1000, step=10, width="small"),
            "a": st.column_config.NumberColumn("a ($/MW²)", min_value=0.001, max_value=0.1, step=0.001, format="%.4f", width="small"),
            "b": st.column_config.NumberColumn("b ($/MW)", min_value=1, max_value=100, step=1, width="small"),
            "c": st.column_config.NumberColumn("c ($)", min_value=0, max_value=200, step=5, width="small"),
            "ramp_up": st.column_config.NumberColumn("Ramp Up (MW/h)", min_value=1, max_value=200, step=5, width="small"),
            "ramp_down": st.column_config.NumberColumn("Ramp Down (MW/h)", min_value=1, max_value=200, step=5, width="small"),
            "emission_rate": st.column_config.NumberColumn("Emission Rate (tons/MWh)", min_value=0.1, max_value=2.0, step=0.05, format="%.3f", width="small")
        },
        width='stretch',  # Changed from use_container_width=True
        num_rows="fixed",
        key="generator_editor"  # Important: Add a unique key
    )
    
    # Check if the data has actually changed before updating
    if not edited_df.equals(df_generators):
        # Convert back to list of dictionaries and update session state
        st.session_state.generators = edited_df.to_dict('records')
        
        # Clear solutions when generator parameters change
        if st.session_state.solutions:
            st.session_state.solutions = {}
            st.info("Generator parameters changed. Previous solutions cleared.")
        
        # Force a rerun to update the display
        st.rerun()
    
    # Add preset buttons
    st.markdown("### 🎯 Generator Presets")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🏭 Mixed Fleet", key="preset_mixed"):
            st.session_state.generators = [
                {'name': 'Coal1', 'type': 'Coal', 'pmin': 50, 'pmax': 400, 'a': 0.008, 'b': 25, 'c': 80, 'ramp_up': 60, 'ramp_down': 60, 'emission_rate': 0.95},
                {'name': 'Gas1', 'type': 'Gas', 'pmin': 20, 'pmax': 250, 'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 100, 'ramp_down': 100, 'emission_rate': 0.45},
                {'name': 'Hydro1', 'type': 'Hydro', 'pmin': 30, 'pmax': 200, 'a': 0.002, 'b': 10, 'c': 20, 'ramp_up': 150, 'ramp_down': 150, 'emission_rate': 0.02}
            ]
            st.session_state.solutions = {}
            st.rerun()
    
    with col2:
        if st.button("⚡ All Gas", key="preset_gas"):
            st.session_state.generators = [
                {'name': 'Gas1', 'type': 'Gas', 'pmin': 20, 'pmax': 200, 'a': 0.012, 'b': 30, 'c': 45, 'ramp_up': 80, 'ramp_down': 80, 'emission_rate': 0.45},
                {'name': 'Gas2', 'type': 'Gas', 'pmin': 25, 'pmax': 250, 'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 90, 'ramp_down': 90, 'emission_rate': 0.48},
                {'name': 'Gas3', 'type': 'Gas', 'pmin': 15, 'pmax': 180, 'a': 0.018, 'b': 40, 'c': 55, 'ramp_up': 75, 'ramp_down': 75, 'emission_rate': 0.50}
            ]
            st.session_state.solutions = {}
            st.rerun()
    
    with col3:
        if st.button("🌊 Hydro Heavy", key="preset_hydro"):
            st.session_state.generators = [
                {'name': 'Hydro1', 'type': 'Hydro', 'pmin': 30, 'pmax': 200, 'a': 0.002, 'b': 8, 'c': 15, 'ramp_up': 120, 'ramp_down': 120, 'emission_rate': 0.02},
                {'name': 'Hydro2', 'type': 'Hydro', 'pmin': 25, 'pmax': 180, 'a': 0.003, 'b': 10, 'c': 20, 'ramp_up': 100, 'ramp_down': 100, 'emission_rate': 0.02},
                {'name': 'Gas1', 'type': 'Gas', 'pmin': 20, 'pmax': 150, 'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 80, 'ramp_down': 80, 'emission_rate': 0.45}
            ]
            st.session_state.solutions = {}
            st.rerun()
    
    with col4:
        if st.button("♻️ Low Emission", key="preset_clean"):
            st.session_state.generators = [
                {'name': 'Nuclear1', 'type': 'Nuclear', 'pmin': 100, 'pmax': 400, 'a': 0.005, 'b': 15, 'c': 100, 'ramp_up': 30, 'ramp_down': 30, 'emission_rate': 0.01},
                {'name': 'Hydro1', 'type': 'Hydro', 'pmin': 30, 'pmax': 200, 'a': 0.002, 'b': 10, 'c': 20, 'ramp_up': 150, 'ramp_down': 150, 'emission_rate': 0.02},
                {'name': 'Gas1', 'type': 'Gas', 'pmin': 20, 'pmax': 180, 'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 100, 'ramp_down': 100, 'emission_rate': 0.40}
            ]
            st.session_state.solutions = {}
            st.rerun()

def _tab_body() -> None:
    render_generator_table()

    # Current setup summary
    st.markdown("### 📋 Current Setup")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Generators", len(st.session_state.generators))

    with col2:
        st.metric("Time Periods", len(st.session_state.demand_profile))

    with col3:
        total_capacity = sum(gen['pmax'] for gen in st.session_state.generators)
        st.metric("Total Capacity", f"{total_capacity} MW")

    with col4:
        max_demand = max(st.session_state.demand_profile)
        st.metric("Peak Demand", f"{max_demand} MW")

    # Demand profile visualization
    st.markdown("### 📈 Demand Profile")
    fig_demand = go.Figure()
    fig_demand.add_trace(go.Scatter(
        x=list(range(len(st.session_state.demand_profile))),
        y=st.session_state.demand_profile,
        mode='lines+markers',
        name='Demand',
        line=dict(color='red', width=3),
        marker=dict(size=8)
    ))

    fig_demand.update_layout(
        title="Load Profile",
        xaxis_title="Time Period",
        yaxis_title="Demand (MW)",
        showlegend=False
    )

    st.plotly_chart(fig_demand, width='stretch')  # Changed from use_container_width=True


def render() -> None:
    dispatch.page(_tab_body)
