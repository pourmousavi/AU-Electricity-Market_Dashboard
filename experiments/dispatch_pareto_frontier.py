"""Dispatch Pareto frontier.

Extracted from week7_ed_viu.py (render_pareto_frontier, tab 5) on 2026-08-12.
The CSS, session state, sidebar and footer shared with the other dispatch
experiments live in experiments/_kit/dispatch.py.
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


def render_pareto_frontier():
    """Render Pareto frontier for ED-5 multi-objective optimization"""
    if "ED-5" not in st.session_state.solutions:
        st.info("Solve ED-5 first to see Pareto frontier analysis.")
        return
    
    st.markdown("## 🎯 ED-5: Pareto Frontier Analysis")
    
    ed5_result = st.session_state.solutions["ED-5"]
    ed5_problem = ed5_result['problem']
    
    if not hasattr(ed5_problem, 'pareto_costs'):
        st.warning("Pareto frontier data not available. Please re-solve ED-5.")
        return
    
    st.info(f"Pareto frontier contains {len(ed5_problem.pareto_costs)} optimal points")
    
    # Pareto frontier plot
    fig_pareto = go.Figure()
    
    # Add Pareto frontier curve
    fig_pareto.add_trace(go.Scatter(
        x=ed5_problem.pareto_costs,
        y=ed5_problem.pareto_emissions,
        mode='lines+markers',
        name='Pareto Frontier',
        line=dict(color='blue', width=3),
        marker=dict(size=8, color='blue', symbol='circle'),
        text=[f"Point {i+1}" for i in range(len(ed5_problem.pareto_costs))],
        hovertemplate="<b>Point %{text}</b><br>" +
                      "Cost: $%{x:,.0f}<br>" +
                      "Emissions: %{y:.1f} tons<br>" +
                      "<extra></extra>"
    ))
    
    # Highlight corner points (pure cost and pure emission)
    if len(ed5_problem.pareto_costs) > 2:
        # Min cost point
        min_cost_idx = np.argmin(ed5_problem.pareto_costs)
        fig_pareto.add_trace(go.Scatter(
            x=[ed5_problem.pareto_costs[min_cost_idx]],
            y=[ed5_problem.pareto_emissions[min_cost_idx]],
            mode='markers+text',
            text=["Min Cost"],
            textposition="top center",
            name='Minimum Cost Solution',
            marker=dict(size=15, color='green', symbol='star'),
        ))
        
        # Min emission point
        min_emission_idx = np.argmin(ed5_problem.pareto_emissions)
        fig_pareto.add_trace(go.Scatter(
            x=[ed5_problem.pareto_costs[min_emission_idx]],
            y=[ed5_problem.pareto_emissions[min_emission_idx]],
            mode='markers+text',
            text=["Min Emissions"],
            textposition="top center",
            name='Minimum Emission Solution',
            marker=dict(size=15, color='lightgreen', symbol='star'),
        ))
    
    # Add other ED solutions for comparison
    comparison_colors = {'ED-2': 'orange', 'ED-3': 'purple', 'ED-4': 'red'}
    
    for prob_type, result in st.session_state.solutions.items():
        if prob_type != "ED-5":
            color = comparison_colors.get(prob_type, 'gray')
            fig_pareto.add_trace(go.Scatter(
                x=[result['total_cost']],
                y=[result['emissions']],
                mode='markers+text',
                text=[prob_type],
                textposition="top center",
                name=f"{prob_type}",
                marker=dict(size=15, color=color, symbol='square')
            ))
    
    fig_pareto.update_layout(
        title=f"Pareto Frontier: Cost vs Emissions Trade-off ({len(ed5_problem.pareto_costs)} points)",
        xaxis_title="Total Cost ($)",
        yaxis_title="Total Emissions (tons)",
        showlegend=True,
        height=600,
        hovermode='closest'
    )
    
    st.plotly_chart(fig_pareto, width='stretch')  # Changed from use_container_width=True
    
    # Summary statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cost_range = max(ed5_problem.pareto_costs) - min(ed5_problem.pareto_costs)
        st.metric("Cost Range", f"${cost_range:,.0f}")
    
    with col2:
        emission_range = max(ed5_problem.pareto_emissions) - min(ed5_problem.pareto_emissions)
        st.metric("Emission Range", f"{emission_range:.1f} tons")
    
    with col3:
        st.metric("Pareto Points", len(ed5_problem.pareto_costs))
    
    with col4:
        # Calculate average trade-off rate
        if len(ed5_problem.pareto_costs) > 1:
            cost_diff = max(ed5_problem.pareto_costs) - min(ed5_problem.pareto_costs)
            emission_diff = max(ed5_problem.pareto_emissions) - min(ed5_problem.pareto_emissions)
            if emission_diff > 0:
                trade_off_rate = cost_diff / emission_diff
                st.metric("Avg Trade-off", f"${trade_off_rate:,.0f}/ton")
            else:
                st.metric("Avg Trade-off", "N/A")
        else:
            st.metric("Avg Trade-off", "N/A")

def _tab_body() -> None:
    render_pareto_frontier()


def render() -> None:
    dispatch.page(_tab_body)
