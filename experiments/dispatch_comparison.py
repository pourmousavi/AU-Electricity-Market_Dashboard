"""Dispatch comparison results.

Extracted from week7_ed_viu.py (render_comparison_results, tab 2) on
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
from experiments._kit.dispatch import get_problem_description

STATE_GROUP = "dispatch"


def render_comparison_results():
    """Render comparison of all solved problems"""
    st.markdown("## 📊 Comparison Results")
    
    if not st.session_state.solutions:
        st.info("Solve problems first to see comparison results.")
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
    
    # Summary table
    st.markdown("### 📋 Summary Comparison")
    
    summary_data = []
    for prob_type, result in st.session_state.solutions.items():
        try:
            if prob_type == "ED-2":
                # Add both unconstrained and ramping-adjusted for ED-2
                unconstrained_cost = result['problem']._calculate_total_cost(result['problem'].solution_unconstrained)
                ramping_violations = count_ramping_violations(result['problem'].solution_unconstrained)
                
                summary_data.append({
                    "Problem": get_problem_description("ED-2"),
                    "Total Cost ($)": f"{unconstrained_cost:,.2f}",
                    "Total Emissions (tons)": f"{result['emissions']:,.2f}",
                    "Ramping Violations": ramping_violations,
                    "Status": "✅ Solved"
                })
                
                summary_data.append({
                    "Problem": get_problem_description("ED-2 (Ramping Adj.)"),
                    "Total Cost ($)": f"{result['total_cost']:,.2f}",
                    "Total Emissions (tons)": f"{result['emissions']:,.2f}",
                    "Ramping Violations": 0,
                    "Status": "✅ Solved"
                })
            else:
                ramping_violations = count_ramping_violations(result['solution'])
                summary_data.append({
                    "Problem": get_problem_description(prob_type),
                    "Total Cost ($)": f"{result['total_cost']:,.2f}",
                    "Total Emissions (tons)": f"{result['emissions']:,.2f}",
                    "Ramping Violations": ramping_violations,
                    "Status": "✅ Solved"
                })
        except IndexError:
            st.error(f"Error processing {prob_type} results. Please re-solve problems.")
            continue
    
    if summary_data:
        df_summary = pd.DataFrame(summary_data)
        st.dataframe(df_summary, width='stretch')  # Changed from use_container_width=True
    
    # Rest of the function remains the same...
    
    # Show ED-2 ramping impact analysis
    if "ED-2" in st.session_state.solutions:
        st.markdown("### 🔄 ED-2 Ramping Impact Analysis")
        
        ed2_result = st.session_state.solutions["ED-2"]
        unconstrained_cost = ed2_result['problem']._calculate_total_cost(ed2_result['problem'].solution_unconstrained)
        ramping_cost = ed2_result['total_cost']
        
        cost_increase = ramping_cost - unconstrained_cost
        cost_increase_pct = (cost_increase / unconstrained_cost) * 100
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cost Increase due to Ramping", f"${cost_increase:,.0f}", f"{cost_increase_pct:+.1f}%")
        
        with col2:
            unconstrained_emissions = ed2_result['problem']._calculate_emissions(ed2_result['problem'].solution_unconstrained)
            emission_change = ed2_result['emissions'] - unconstrained_emissions
            st.metric("Emission Change", f"{emission_change:+.1f} tons")
        
        with col3:
            # Count ramping violations
            ramping_violations = count_ramping_violations(ed2_result['problem'].solution_unconstrained)
            st.metric("Ramping Violations Fixed", f"{ramping_violations}")
    
    # Side-by-side generation dispatch
    st.markdown("### ⚡ Generation Dispatch Comparison")
    
    # Create subplots for each ED type (including both ED-2 variants)
    problem_types = list(st.session_state.solutions.keys())
    
    # For ED-2, we'll show both unconstrained and ramping-adjusted
    plot_data = []
    for prob_type in problem_types:
        if prob_type == "ED-2":
            plot_data.append((f"{prob_type} (Unconstrained)", st.session_state.solutions[prob_type]['problem'].solution_unconstrained))
            plot_data.append((f"{prob_type} (Ramping Adj.)", st.session_state.solutions[prob_type]['solution']))
        else:
            plot_data.append((prob_type, st.session_state.solutions[prob_type]['solution']))
    
    n_plots = len(plot_data)
    
    if n_plots > 0:
        # Determine subplot layout
        if n_plots <= 4:
            rows, cols = 2, 2
        elif n_plots <= 6:
            rows, cols = 2, 3
        else:
            rows, cols = 3, 3
        
        fig = make_subplots(
            rows=rows, cols=cols,
            subplot_titles=[f"{title}" for title, _ in plot_data],
            vertical_spacing=0.12,
            horizontal_spacing=0.08
        )
        
        # Define custom colors that are more distinctive and visible
        custom_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']  # Blue, Orange, Green, Red, Purple, Brown
        time_periods = list(range(len(st.session_state.demand_profile)))
        
        for idx, (title, solution) in enumerate(plot_data):
            row = (idx // cols) + 1
            col = (idx % cols) + 1
            
            # Plot each generator
            for i, gen in enumerate(st.session_state.generators):
                fig.add_trace(
                    go.Scatter(
                        x=time_periods,
                        y=solution[i, :],
                        mode='lines+markers',
                        name=gen['name'],
                        line=dict(color=custom_colors[i % len(custom_colors)], width=2),
                        showlegend=(idx == 0)  # Only show legend for first subplot
                    ),
                    row=row, col=col
                )
            
            # Add demand line
            fig.add_trace(
                go.Scatter(
                    x=time_periods,
                    y=st.session_state.demand_profile,
                    mode='lines',
                    name='Demand',
                    line=dict(color='red', width=3, dash='dash'),
                    showlegend=(idx == 0)
                ),
                row=row, col=col
            )
        
        fig.update_layout(
            height=600,
            title_text="Generation Dispatch by ED Type",
            showlegend=True
        )
        
        # Update axes labels
        for i in range(1, rows+1):
            for j in range(1, cols+1):
                fig.update_xaxes(title_text="Time Period" if i == rows else "", row=i, col=j)
                fig.update_yaxes(title_text="Power (MW)" if j == 1 else "", row=i, col=j)
        
        st.plotly_chart(fig, width='stretch')  # Changed from use_container_width=True

def count_ramping_violations(solution):
    """Count number of ramping violations in unconstrained solution"""
    violations = 0
    n_time = solution.shape[1]
    n_gen_in_solution = solution.shape[0]  # Number of generators in the solution
    
    for t in range(1, n_time):
        # Only iterate over generators that exist in the solution
        for i in range(min(n_gen_in_solution, len(st.session_state.generators))):
            if i < len(st.session_state.generators):  # Extra safety check
                gen = st.session_state.generators[i]
                power_change = solution[i, t] - solution[i, t-1]
                
                if power_change > gen['ramp_up']:
                    violations += 1
                elif power_change < -gen['ramp_down']:
                    violations += 1
    
    return violations

def _tab_body() -> None:
    render_comparison_results()


def render() -> None:
    dispatch.page(_tab_body)
