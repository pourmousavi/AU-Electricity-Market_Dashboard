"""Shared duality page for week 6.

Extracted from week6_duality.py (module-level body, minus the tab block at
lines 391-463) on 2026-08-12. The three duality experiments -- strong_duality,
weak_duality and duality_theorems -- each render this page plus their own tab
body.
"""
from typing import Callable, Optional

import streamlit as st
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from scipy.optimize import linprog
import sympy as sp


def page(tab_body: Optional[Callable[[str], None]] = None) -> tuple:
    """Render the shared duality page and return what the tab sections need.

    ``tab_body`` renders the calling experiment's own tab content. It is invoked
    at the point where week6_duality.py rendered its ``st.tabs`` block, so the
    sections below it still appear after it, as they do today. It is handed
    ``prob_type`` because the duality_theorems body branches on it.
    """
    # Add custom CSS for better formatting
    st.markdown("""
    <style>
    .latex-container {
        background-color: #f8f9fa;
        border-left: 4px solid #007acc;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .problem-container {
        background-color: #e8f4fd;
        padding: 20px;
        border-radius: 10px;
        margin: 15px 0;
    }
    .dual-container {
        background-color: #fff2e8;
        padding: 20px;
        border-radius: 10px;
        margin: 15px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # Sidebar
    st.sidebar.title("📊 Duality Theory Dashboard")
    st.sidebar.markdown("**Electricity Market & Power System Operation**")
    st.sidebar.markdown("**ELEC ENG 4087/7087**")
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Instructor:** Ali Pourmousavi Kani")
    st.sidebar.markdown("**Topic:** Linear Programming Duality")

    # Main title
    st.title("Linear Programming Duality Theory")
    st.markdown("**Interactive visualization of primal-dual relationships with strong and weak duality demonstrations**")

    # Problem setup section
    st.header("🔧 Problem Configuration")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Objective Function")
        c1 = st.slider("c₁ (coefficient of x₁)", -5.0, 5.0, 3.0, 0.1)
        c2 = st.slider("c₂ (coefficient of x₂)", -5.0, 5.0, 2.0, 0.1)

    with col2:
        st.subheader("Problem Type")
        prob_type = st.selectbox("Optimization Type", ["Maximize", "Minimize"])

    # Now we can use prob_type to set the inequality sign
    inequality_sign = "≤" if prob_type == "Maximize" else "≥"

    with col1:    
        st.subheader(f"Constraint 1: a₁x₁ + b₁x₂ {inequality_sign} d₁")
        a1 = st.slider("a₁", 0.1, 5.0, 1.0, 0.1)
        b1 = st.slider("b₁", 0.1, 5.0, 1.0, 0.1)
        d1 = st.slider("d₁", 1.0, 10.0, 4.0, 0.1)

    with col2:    
        st.subheader(f"Constraint 2: a₂x₁ + b₂x₂ {inequality_sign} d₂")
        a2 = st.slider("a₂", 0.1, 5.0, 2.0, 0.1)
        b2 = st.slider("b₂", 0.1, 5.0, 1.0, 0.1)
        d2 = st.slider("d₂", 1.0, 10.0, 6.0, 0.1)

    # Convert to standard form based on problem type
    if prob_type == "Maximize":
        obj_sign = 1
        obj_text = "maximize"
        dual_obj_text = "minimize"
        c_dual = [d1, d2]
        A_dual = [[a1, a2], [b1, b2]]
        b_dual = [c1, c2]
    else:
        obj_sign = -1
        obj_text = "minimize"
        dual_obj_text = "maximize"
        c_dual = [-d1, -d2]
        A_dual = [[-a1, -a2], [-b1, -b2]]
        b_dual = [-c1, -c2]

    # Problem formulation section
    st.header("📝 Problem Formulation")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="problem-container">', unsafe_allow_html=True)
        st.markdown("### **Primal Problem**")
        
        # LaTeX formulation
        if prob_type == "Maximize":
            primal_latex = f"""
            \\begin{{align*}}
            \\text{{maximize}} & \\quad {c1:.1f}x_1 + {c2:.1f}x_2 \\\\
            \\text{{subject to}} & \\quad {a1:.1f}x_1 + {b1:.1f}x_2 \\leq {d1:.1f} \\\\
            & \\quad {a2:.1f}x_1 + {b2:.1f}x_2 \\leq {d2:.1f} \\\\
            & \\quad x_1, x_2 \\geq 0
            \\end{{align*}}
            """
        else:
            primal_latex = f"""
            \\begin{{align*}}
            \\text{{minimize}} & \\quad {c1:.1f}x_1 + {c2:.1f}x_2 \\\\
            \\text{{subject to}} & \\quad {a1:.1f}x_1 + {b1:.1f}x_2 \\geq {d1:.1f} \\\\
            & \\quad {a2:.1f}x_1 + {b2:.1f}x_2 \\geq {d2:.1f} \\\\
            & \\quad x_1, x_2 \\geq 0
            \\end{{align*}}
            """
        
        st.latex(primal_latex)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="dual-container">', unsafe_allow_html=True)
        st.markdown("### **Dual Problem**")
        
        # Dual formulation
        if prob_type == "Maximize":
            dual_latex = f"""
            \\begin{{align*}}
            \\text{{minimize}} & \\quad {d1:.1f}\\lambda_1 + {d2:.1f}\\lambda_2 \\\\
            \\text{{subject to}} & \\quad {a1:.1f}\\lambda_1 + {a2:.1f}\\lambda_2 \\geq {c1:.1f} \\\\
            & \\quad {b1:.1f}\\lambda_1 + {b2:.1f}\\lambda_2 \\geq {c2:.1f} \\\\
            & \\quad \\lambda_1, \\lambda_2 \\geq 0
            \\end{{align*}}
            """
        else:
            dual_latex = f"""
            \\begin{{align*}}
            \\text{{maximize}} & \\quad {d1:.1f}\\lambda_1 + {d2:.1f}\\lambda_2 \\\\
            \\text{{subject to}} & \\quad {a1:.1f}\\lambda_1 + {a2:.1f}\\lambda_2 \\leq {c1:.1f} \\\\
            & \\quad {b1:.1f}\\lambda_1 + {b2:.1f}\\lambda_2 \\leq {c2:.1f} \\\\
            & \\quad \\lambda_1, \\lambda_2 \\geq 0
            \\end{{align*}}
            """
        
        st.latex(dual_latex)
        st.markdown('</div>', unsafe_allow_html=True)

    # Solve problems
    def solve_primal():
        if prob_type == "Maximize":
            # Convert to minimization for scipy
            c = [-c1, -c2]
            A_ub = [[a1, b1], [a2, b2]]
            b_ub = [d1, d2]
        else:
            c = [c1, c2]
            A_ub = [[-a1, -b1], [-a2, -b2]]
            b_ub = [-d1, -d2]
        
        bounds = [(0, None), (0, None)]
        
        try:
            result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
            if result.success:
                if prob_type == "Maximize":
                    return result.x, -result.fun
                else:
                    return result.x, result.fun
        except:
            pass
        return None, None

    def solve_dual():
        if prob_type == "Maximize":
            c = [d1, d2]
            A_ub = [[-a1, -a2], [-b1, -b2]]
            b_ub = [-c1, -c2]
        else:
            c = [-d1, -d2]
            A_ub = [[a1, a2], [b1, b2]]
            b_ub = [c1, c2]
        
        bounds = [(0, None), (0, None)]
        
        try:
            result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
            if result.success:
                if prob_type == "Maximize":
                    return result.x, result.fun
                else:
                    return result.x, -result.fun
        except:
            pass
        return None, None

    # Solve both problems
    primal_x, primal_obj = solve_primal()
    dual_lambda, dual_obj = solve_dual()

    # Results section
    st.header("🎯 Optimal Solutions")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.subheader("Primal Solution")
        if primal_x is not None:
            st.write(f"**x₁*** = {primal_x[0]:.3f}")
            st.write(f"**x₂*** = {primal_x[1]:.3f}")
            st.write(f"**Objective Value** = {primal_obj:.3f}")
        else:
            st.write("No feasible solution found")

    with col2:
        st.subheader("Dual Solution")
        if dual_lambda is not None:
            st.write(f"**λ₁*** = {dual_lambda[0]:.3f}")
            st.write(f"**λ₂*** = {dual_lambda[1]:.3f}")
            st.write(f"**Objective Value** = {dual_obj:.3f}")
        else:
            st.write("No feasible solution found")

    with col3:
        st.subheader("Duality Analysis")
        if primal_obj is not None and dual_obj is not None:
            gap = abs(primal_obj - dual_obj)
            st.write(f"**Duality Gap** = {gap:.6f}")
            
            if gap < 1e-5:
                st.success("✅ **Strong Duality** achieved!")
                st.write("Primal and dual optimal values are equal")
            else:
                st.warning("⚠️ **Weak Duality** only")
                st.write(f"Gap exists between primal and dual")
            
            # Weak duality check
            if prob_type == "Maximize":
                if primal_obj <= dual_obj + 1e-10:
                    st.info("✓ Weak duality condition satisfied: Primal ≤ Dual")
            else:
                if primal_obj >= dual_obj - 1e-10:
                    st.info("✓ Weak duality condition satisfied: Primal ≥ Dual")

    # 3D Visualization
    st.header("📊 3D Feasible Region Visualization")

    # Create 3D plot
    def create_3d_plot():
        # Create grid for the plots
        x1_range = np.linspace(0, 8, 50)
        x2_range = np.linspace(0, 8, 50)
        X1, X2 = np.meshgrid(x1_range, x2_range)
        
        # Objective function surface
        Z = c1 * X1 + c2 * X2
        
        fig = go.Figure()
        
        # Add objective function surface (blue)
        fig.add_trace(go.Surface(
            x=X1, y=X2, z=Z,
            colorscale='Blues',
            opacity=0.6,
            name='Objective Function Surface',  # Added clear name
            showlegend=True,  # Show in legend
            showscale=False,
            hoverinfo='skip'  # Reduce clutter in hover text
        ))
        
        # Define feasible region for primal
        feasible_mask = np.ones_like(X1, dtype=bool)
        
        if prob_type == "Maximize":
            feasible_mask &= (a1 * X1 + b1 * X2 <= d1)
            feasible_mask &= (a2 * X1 + b2 * X2 <= d2)
        else:
            feasible_mask &= (a1 * X1 + b1 * X2 >= d1)
            feasible_mask &= (a2 * X1 + b2 * X2 >= d2)
        
        feasible_mask &= (X1 >= 0) & (X2 >= 0)
        
        # Create feasible region surface (red)
        Z_feasible = np.full_like(Z, np.nan)
        Z_feasible[feasible_mask] = Z[feasible_mask]
        
        fig.add_trace(go.Surface(
            x=X1, y=X2, z=Z_feasible,
            colorscale='Reds',
            opacity=0.8,
            name='Feasible Region Surface',  # Added clear name
            showlegend=True,  # Show in legend
            showscale=False,
            hoverinfo='skip'  # Reduce clutter in hover text
        ))
        
        # Define constraint lines for 3D plot
        x1_line = np.linspace(0, 8, 100)
        
        # Constraint 1 line
        if b1 != 0:
            x2_line1 = (d1 - a1 * x1_line) / b1
            valid_idx1 = (x2_line1 >= 0) & (x2_line1 <= 8)
            z1_line = c1 * x1_line + c2 * x2_line1
            
            fig.add_trace(go.Scatter3d(
                x=x1_line[valid_idx1],
                y=x2_line1[valid_idx1],
                z=z1_line[valid_idx1],
                mode='lines',
                line=dict(color='red', width=8),
                name=f'Constraint 1: {a1:.1f}x₁ + {b1:.1f}x₂ = {d1:.1f}'
            ))
        
        # Constraint 2 line
        if b2 != 0:
            x2_line2 = (d2 - a2 * x1_line) / b2
            valid_idx2 = (x2_line2 >= 0) & (x2_line2 <= 8)
            z2_line = c1 * x1_line + c2 * x2_line2
            
            fig.add_trace(go.Scatter3d(
                x=x1_line[valid_idx2],
                y=x2_line2[valid_idx2],
                z=z2_line[valid_idx2],
                mode='lines',
                line=dict(color='orange', width=8),
                name=f'Constraint 2: {a2:.1f}x₁ + {b2:.1f}x₂ = {d2:.1f}'
            ))
        
        # Add optimal point if found
        if primal_x is not None:
            opt_z = c1 * primal_x[0] + c2 * primal_x[1]
            fig.add_trace(go.Scatter3d(
                x=[primal_x[0]],
                y=[primal_x[1]],
                z=[opt_z],
                mode='markers',
                marker=dict(color='gold', size=12, symbol='diamond'),
                name=f'Optimal Point ({primal_x[0]:.2f}, {primal_x[1]:.2f})'
            ))
        
        # Update layout
        fig.update_layout(
            title={
                'text': "3D Visualization: Objective Function and Feasible Region",
                'x': 0.5,
                'xanchor': 'center'
            },
            scene=dict(
                xaxis_title="x₁",
                yaxis_title="x₂", 
                zaxis_title="Objective Value",
                camera=dict(
                    up=dict(x=0, y=0, z=1),
                    center=dict(x=0, y=0, z=0),
                    eye=dict(x=1.5, y=1.5, z=1.5)
                ),
                aspectmode='cube'
            ),
            width=900,
            height=700,
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(255, 255, 255, 0.8)"  # Semi-transparent white background
            )
        )
        
        return fig

    # Display the 3D plot
    fig_3d = create_3d_plot()
    st.plotly_chart(fig_3d, use_container_width=True)

    # Educational content
    st.header("📚 Understanding Duality Scenarios")

    # tab bodies now live in the three duality experiment modules; each one
    # renders here so that the sections below still follow it on the page
    if tab_body is not None:
        tab_body(prob_type)

    # Shadow prices explanation with current example
    st.header("💰 Shadow Prices in Current Example")

    if primal_x is not None and dual_lambda is not None:
        st.markdown(f"""
        **Current shadow prices:**
        - λ₁* = {dual_lambda[0]:.3f} (Constraint 1)
        - λ₂* = {dual_lambda[1]:.3f} (Constraint 2)
        
        **Economic interpretation:**
        - If we could relax constraint 1 by one unit (from {d1:.1f} to {d1+1:.1f}), 
          the objective would improve by approximately {dual_lambda[0]:.3f}
        - If we could relax constraint 2 by one unit (from {d2:.1f} to {d2+1:.1f}), 
          the objective would improve by approximately {dual_lambda[1]:.3f}
        """)
        
        if dual_lambda[0] > 1e-6:
            st.info(f"🔴 Constraint 1 is **binding** (shadow price = {dual_lambda[0]:.3f})")
        else:
            st.info("⚪ Constraint 1 is **not binding** (shadow price = 0)")
            
        if dual_lambda[1] > 1e-6:
            st.info(f"🔴 Constraint 2 is **binding** (shadow price = {dual_lambda[1]:.3f})")
        else:
            st.info("⚪ Constraint 2 is **not binding** (shadow price = 0)")

    # Interactive experiments
    st.header("🧪 Interactive Experiments")

    experiment = st.selectbox(
        "Select an experiment to understand duality:",
        [
            "Standard LP - Strong Duality",
            "Unbounded Primal - Infeasible Dual", 
            "Infeasible Primal - Unbounded Dual",
            "Custom Parameters"
        ]
    )

    if experiment == "Standard LP - Strong Duality":
        st.info("✅ This shows the normal case where both problems have optimal solutions with equal objective values.")
    elif experiment == "Unbounded Primal - Infeasible Dual":
        st.warning("⚠️ The primal can increase indefinitely, making the dual infeasible. This demonstrates weak duality limits.")
    elif experiment == "Infeasible Primal - Unbounded Dual":
        st.error("❌ Contradictory constraints make the primal infeasible, causing the dual to be unbounded.")
    else:
        st.info("🔧 Use the custom parameters above to explore different scenarios.")

    st.markdown("""
    **Try these experiments:**
    1. **Strong Duality**: Use the first example to see equal objective values
    2. **Constraint Binding**: Change d₁ or d₂ and observe shadow price changes
    3. **Unbounded Problems**: Use negative constraint coefficients to create unbounded cases
    4. **Infeasible Problems**: Create contradictory constraints
    """)

    # Connection to electricity markets
    st.header("⚡ Connection to Electricity Markets")

    st.markdown("""
    **In electricity markets, duality theory provides the foundation for pricing:**

    - **Primal Problem**: Economic dispatch (minimize generation cost)
    - **Dual Variables**: Locational Marginal Prices (LMPs)
    - **Shadow Prices**: Value of transmission capacity, generation limits
    - **Strong Duality**: Ensures market clearing prices exist

    **Key Applications:**
    1. **LMP Calculation**: Dual variables of power balance constraints
    2. **Congestion Pricing**: Shadow prices of transmission limits  
    3. **Reserve Pricing**: Dual variables of reserve requirements
    4. **Capacity Markets**: Shadow prices of reliability constraints
    """)

    # Footer
    st.markdown("---")
    st.markdown("""
    **Educational Dashboard for ELEC ENG 4087/7087**  
    *This interactive tool demonstrates linear programming duality theory essential for understanding electricity market operations and power system optimization.*

    **Next Topics:** Mixed-Integer Linear Programming, Unit Commitment, Optimal Power Flow
    """)

    return primal_x, primal_obj, dual_lambda, dual_obj
