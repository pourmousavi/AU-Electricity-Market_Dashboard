"""Dispatch individual generator analysis.

Extracted from week7_ed_viu.py (render_individual_generator_analysis, tab 4) on
2026-08-12. The CSS, session state, sidebar and footer shared with the other
dispatch experiments live in experiments/_kit/dispatch.py.
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
from experiments._kit.dispatch import get_problem_name, get_problem_description

STATE_GROUP = "dispatch"


def render_individual_generator_analysis():
    """Render individual generator dispatch analysis"""
    st.markdown("## 🏭 Individual Generator Analysis")
    
    if not st.session_state.solutions:
        st.info("No solutions available for analysis.")
        return
    
    # Generator selection
    selected_gen = st.selectbox(
        "Select Generator for Detailed Analysis",
        options=range(len(st.session_state.generators)),
        format_func=lambda x: st.session_state.generators[x]['name']
    )
    
    gen_name = st.session_state.generators[selected_gen]['name']
    
    # Create comparison chart for selected generator
    fig = go.Figure()
    
    time_periods = list(range(len(st.session_state.demand_profile)))
    colors = ['#ff9999', '#ff6666', '#ff7f0e', '#2ca02c', '#d62728']
    color_idx = 0
    
    for prob_type, result in st.session_state.solutions.items():
        if prob_type == "ED-2":
            # Show both unconstrained and ramping-adjusted for ED-2
            unconstrained_solution = result['problem'].solution_unconstrained
            adjusted_solution = result['solution']
            
            # Unconstrained ED-2
            fig.add_trace(go.Scatter(
                x=time_periods,
                y=unconstrained_solution[selected_gen, :],
                mode='lines+markers',
                name=f"ED-2 (Unconstrained)",
                line=dict(color=colors[color_idx], width=2, dash='dot'),
                marker=dict(size=6)
            ))
            color_idx += 1
            
            # Ramping-adjusted ED-2
            fig.add_trace(go.Scatter(
                x=time_periods,
                y=adjusted_solution[selected_gen, :],
                mode='lines+markers',
                name=f"ED-2 (Ramping Adj.)",
                line=dict(color=colors[color_idx], width=3),
                marker=dict(size=8)
            ))
            color_idx += 1
        else:
            solution = result['solution']
            fig.add_trace(go.Scatter(
                x=time_periods,
                y=solution[selected_gen, :],
                mode='lines+markers',
                name=f"{prob_type}: {get_problem_name(prob_type)}",
                line=dict(color=colors[color_idx], width=3),
                marker=dict(size=8)
            ))
            color_idx += 1
    
    # Add generator limits
    gen = st.session_state.generators[selected_gen]
    fig.add_hline(y=gen['pmax'], line_dash="dash", line_color="red", 
                  annotation_text=f"Pmax: {gen['pmax']} MW")
    fig.add_hline(y=gen['pmin'], line_dash="dash", line_color="orange", 
                  annotation_text=f"Pmin: {gen['pmin']} MW")
    
    fig.update_layout(
        title=f"Dispatch Profile Comparison - {gen_name}",
        xaxis_title="Time Period",
        yaxis_title="Power Output (MW)",
        showlegend=True,
        height=500
    )
    
    st.plotly_chart(fig, width='stretch')  # Changed from use_container_width=True
    
    # Generator utilization table
    st.markdown(f"### 📊 {gen_name} Utilization Summary")
    
    util_data = {}
    for prob_type, result in st.session_state.solutions.items():
        if prob_type == "ED-2":
            # Add both versions for ED-2
            unconstrained_solution = result['problem'].solution_unconstrained
            adjusted_solution = result['solution']
            
            # Unconstrained
            gen_output = unconstrained_solution[selected_gen, :]
            avg_output = np.mean(gen_output)
            max_output = np.max(gen_output)
            capacity_factor = avg_output / gen['pmax'] * 100
            
            util_data[get_problem_description("ED-2")] = {
                'Avg Output (MW)': f"{avg_output:.1f}",
                'Max Output (MW)': f"{max_output:.1f}",
                'Capacity Factor (%)': f"{capacity_factor:.1f}",
                'Total Energy (MWh)': f"{np.sum(gen_output):.1f}"
            }
            
            # Ramping-adjusted
            gen_output = adjusted_solution[selected_gen, :]
            avg_output = np.mean(gen_output)
            max_output = np.max(gen_output)
            capacity_factor = avg_output / gen['pmax'] * 100
            
            util_data[get_problem_description("ED-2 (Ramping Adj.)")] = {
                'Avg Output (MW)': f"{avg_output:.1f}",
                'Max Output (MW)': f"{max_output:.1f}",
                'Capacity Factor (%)': f"{capacity_factor:.1f}",
                'Total Energy (MWh)': f"{np.sum(gen_output):.1f}"
            }
        else:
            solution = result['solution']
            gen_output = solution[selected_gen, :]
            
            avg_output = np.mean(gen_output)
            max_output = np.max(gen_output)
            capacity_factor = avg_output / gen['pmax'] * 100
            
            util_data[get_problem_description(prob_type)] = {
                'Avg Output (MW)': f"{avg_output:.1f}",
                'Max Output (MW)': f"{max_output:.1f}",
                'Capacity Factor (%)': f"{capacity_factor:.1f}",
                'Total Energy (MWh)': f"{np.sum(gen_output):.1f}"
            }
    
    util_df = pd.DataFrame(util_data).T
    st.dataframe(util_df, width='stretch')  # Changed from use_container_width=True
    
    # Ramping analysis for selected generator
    if "ED-2" in st.session_state.solutions:
        st.markdown(f"### 🔄 {gen_name} Ramping Analysis")
        
        ed2_result = st.session_state.solutions["ED-2"]
        unconstrained = ed2_result['problem'].solution_unconstrained[selected_gen, :]
        adjusted = ed2_result['solution'][selected_gen, :]
        
        # Create ramping comparison chart
        fig_ramp = go.Figure()
        
        # Calculate ramping rates
        unconstrained_ramp = np.diff(unconstrained)
        adjusted_ramp = np.diff(adjusted)
        ramp_periods = list(range(1, len(st.session_state.demand_profile)))
        
        fig_ramp.add_trace(go.Scatter(
            x=ramp_periods,
            y=unconstrained_ramp,
            mode='lines+markers',
            name='Unconstrained Ramping',
            line=dict(color='lightcoral', width=2),
            marker=dict(size=6)
        ))
        
        fig_ramp.add_trace(go.Scatter(
            x=ramp_periods,
            y=adjusted_ramp,
            mode='lines+markers',
            name='Ramping-Adjusted',
            line=dict(color='red', width=3),
            marker=dict(size=8)
        ))
        
        # Add ramping limits
        fig_ramp.add_hline(y=gen['ramp_up'], line_dash="dash", line_color="green", 
                          annotation_text=f"Ramp Up Limit: {gen['ramp_up']} MW/h")
        fig_ramp.add_hline(y=-gen['ramp_down'], line_dash="dash", line_color="orange", 
                          annotation_text=f"Ramp Down Limit: -{gen['ramp_down']} MW/h")
        
        fig_ramp.update_layout(
            title=f"{gen_name} - Ramping Rate Comparison",
            xaxis_title="Time Period Transition",
            yaxis_title="Ramping Rate (MW/h)",
            showlegend=True,
            height=400
        )
        
        st.plotly_chart(fig_ramp, width='stretch')  # Changed from use_container_width=True
        
        # Ramping statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            violations_up = np.sum(unconstrained_ramp > gen['ramp_up'])
            st.metric("Ramp Up Violations", violations_up)
        
        with col2:
            violations_down = np.sum(unconstrained_ramp < -gen['ramp_down'])
            st.metric("Ramp Down Violations", violations_down)
        
        with col3:
            max_violation = max(
                np.max(unconstrained_ramp) - gen['ramp_up'] if np.max(unconstrained_ramp) > gen['ramp_up'] else 0,
                np.abs(np.min(unconstrained_ramp)) - gen['ramp_down'] if np.min(unconstrained_ramp) < -gen['ramp_down'] else 0
            )
            st.metric("Max Violation (MW/h)", f"{max_violation:.1f}")

def _tab_body() -> None:
    render_individual_generator_analysis()


def render() -> None:
    dispatch.page(_tab_body)
