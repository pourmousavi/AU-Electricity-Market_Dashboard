"""Dispatch detailed analysis.

Extracted from week7_ed_viu.py (render_detailed_analysis, tab 3) on
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
from experiments._kit.dispatch import get_problem_name

STATE_GROUP = "dispatch"


def render_detailed_analysis():
    """Render detailed analysis of results"""
    st.markdown("## 🔍 Detailed Analysis")
    
    if not st.session_state.solutions:
        st.info("No solutions available for analysis.")
        return
    
    # Check if solutions are compatible with current configuration
    current_n_gen = len(st.session_state.generators)
    current_n_time = len(st.session_state.demand_profile)
    
    for prob_type, result in st.session_state.solutions.items():
        solution_shape = result['solution'].shape
        
        if (solution_shape[0] != current_n_gen or 
            solution_shape[1] != current_n_time):
            st.warning(f"Solutions are incompatible with current configuration. Please re-solve problems.")
            st.session_state.solutions = {}
            return
    
    # Cost comparison chart (including ED-2 variants)
    st.markdown("### 💰 Cost Comparison")
    
    costs = []
    problem_labels = []
    
    for prob_type, result in st.session_state.solutions.items():
        if prob_type == "ED-2":
            # Show both unconstrained and ramping-adjusted costs
            unconstrained_cost = result['problem']._calculate_total_cost(result['problem'].solution_unconstrained)
            costs.extend([unconstrained_cost, result['total_cost']])
            problem_labels.extend([f"ED-2 (Unconstrained)", f"ED-2 (Ramping Adj.)"])
        else:
            costs.append(result['total_cost'])
            problem_labels.append(f"{prob_type}: {get_problem_name(prob_type)}")
    
    fig_cost = go.Figure(data=[
        go.Bar(
            x=problem_labels,
            y=costs,
            text=[f"${c:,.0f}" for c in costs],
            textposition='auto',
            marker_color=['#ff9999', '#ff6666', '#ff7f0e', '#2ca02c', '#d62728']  # Different shades for ED-2 variants
        )
    ])
    
    fig_cost.update_layout(
        title="Total Cost by ED Type",
        xaxis_title="Problem Type",
        yaxis_title="Total Cost ($)",
        showlegend=False,
        xaxis_tickangle=-45
    )
    
    st.plotly_chart(fig_cost, width='stretch')  # Changed from use_container_width=True
    
    # Emission comparison
    st.markdown("### 🌱 Emission Comparison")
    
    emissions = []
    emission_labels = []
    
    for prob_type, result in st.session_state.solutions.items():
        if prob_type == "ED-2":
            # Show both unconstrained and ramping-adjusted emissions
            unconstrained_emissions = result['problem']._calculate_emissions(result['problem'].solution_unconstrained)
            emissions.extend([unconstrained_emissions, result['emissions']])
            emission_labels.extend([f"ED-2 (Unconstrained)", f"ED-2 (Ramping Adj.)"])
        else:
            emissions.append(result['emissions'])
            emission_labels.append(f"{prob_type}: {get_problem_name(prob_type)}")
    
    fig_emission = go.Figure(data=[
        go.Bar(
            x=emission_labels,
            y=emissions,
            text=[f"{e:.1f} tons" for e in emissions],
            textposition='auto',
            marker_color=['#cccccc', '#999999', '#e377c2', '#7f7f7f', '#bcbd22']
        )
    ])
    
    fig_emission.update_layout(
        title="Total Emissions by ED Type",
        xaxis_title="Problem Type",
        yaxis_title="Total Emissions (tons)",
        showlegend=False,
        xaxis_tickangle=-45
    )
    
    st.plotly_chart(fig_emission, width='stretch')  # Changed from use_container_width=True
    
    # Cost vs Emission scatter plot
    st.markdown("### ⚖️ Cost vs Emission Trade-off")
    
    fig_scatter = go.Figure()
    
    # Color mapping for different problem types
    colors = {'ED-2': 'red', 'ED-3': 'blue', 'ED-4': 'green', 'ED-5': 'purple'}
    
    for prob_type, result in st.session_state.solutions.items():
        if prob_type == "ED-2":
            # Add both points for ED-2
            unconstrained_cost = result['problem']._calculate_total_cost(result['problem'].solution_unconstrained)
            unconstrained_emissions = result['problem']._calculate_emissions(result['problem'].solution_unconstrained)
            
            # Unconstrained point
            fig_scatter.add_trace(go.Scatter(
                x=[unconstrained_emissions],
                y=[unconstrained_cost],
                mode='markers+text',
                name="ED-2 (Unconstrained)",
                text=["ED-2 (Unc.)"],
                textposition="top center",
                marker=dict(size=15, symbol='circle', color='lightcoral')
            ))
            
            # Ramping-adjusted point
            fig_scatter.add_trace(go.Scatter(
                x=[result['emissions']],
                y=[result['total_cost']],
                mode='markers+text',
                name="ED-2 (Ramping Adj.)",
                text=["ED-2 (Ramp)"],
                textposition="top center",
                marker=dict(size=15, symbol='diamond', color='red')
            ))
            
            # REMOVED: Arrow showing ramping impact - this was causing the visual issue
            
        else:
            fig_scatter.add_trace(go.Scatter(
                x=[result['emissions']],
                y=[result['total_cost']],
                mode='markers+text',
                name=get_problem_name(prob_type),
                text=[prob_type],
                textposition="top center",
                marker=dict(size=15, symbol='circle', color=colors.get(prob_type, 'gray'))
            ))
    
    fig_scatter.update_layout(
        title="Cost vs Emission Trade-off Analysis",
        xaxis_title="Total Emissions (tons)",
        yaxis_title="Total Cost ($)",
        showlegend=True
    )
    
    st.plotly_chart(fig_scatter, width='stretch')  # Changed from use_container_width=True
    
    # ED-2 Ramping Impact Detailed Analysis
    if "ED-2" in st.session_state.solutions:
        st.markdown("### 🔄 ED-2 Ramping Impact Detailed Analysis")
        
        ed2_result = st.session_state.solutions["ED-2"]
        unconstrained_solution = ed2_result['problem'].solution_unconstrained
        adjusted_solution = ed2_result['solution']
        
        # Create ramping violation analysis
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Ramping Violations in Unconstrained Solution:**")
            
            violation_data = []
            for t in range(1, len(st.session_state.demand_profile)):
                for i, gen in enumerate(st.session_state.generators):
                    power_change = unconstrained_solution[i, t] - unconstrained_solution[i, t-1]
                    
                    if power_change > gen['ramp_up']:
                        violation_data.append({
                            'Time': f"{t-1} → {t}",
                            'Generator': gen['name'],
                            'Violation': f"Ramp Up: {power_change:.1f} > {gen['ramp_up']}",
                            'Excess': power_change - gen['ramp_up']
                        })
                    elif power_change < -gen['ramp_down']:
                        violation_data.append({
                            'Time': f"{t-1} → {t}",
                            'Generator': gen['name'],
                            'Violation': f"Ramp Down: {-power_change:.1f} > {gen['ramp_down']}",
                            'Excess': -power_change - gen['ramp_down']
                        })
            
            if violation_data:
                violation_df = pd.DataFrame(violation_data)
                st.dataframe(violation_df, width='stretch')  # Changed from use_container_width=True
            else:
                st.success("No ramping violations found!")
        
        with col2:
            st.markdown("**Generator Dispatch Changes:**")
            
            # Show max changes for each generator
            change_data = []
            for i, gen in enumerate(st.session_state.generators):
                unconstrained_max = np.max(unconstrained_solution[i, :])
                adjusted_max = np.max(adjusted_solution[i, :])
                unconstrained_avg = np.mean(unconstrained_solution[i, :])
                adjusted_avg = np.mean(adjusted_solution[i, :])
                
                change_data.append({
                    'Generator': gen['name'],
                    'Max Change': f"{adjusted_max - unconstrained_max:+.1f} MW",
                    'Avg Change': f"{adjusted_avg - unconstrained_avg:+.1f} MW",
                    'Energy Change': f"{np.sum(adjusted_solution[i, :]) - np.sum(unconstrained_solution[i, :]):+.1f} MWh"
                })
            
            change_df = pd.DataFrame(change_data)
            st.dataframe(change_df, width='stretch')  # Changed from use_container_width=True

def _tab_body() -> None:
    render_detailed_analysis()


def render() -> None:
    dispatch.page(_tab_body)
