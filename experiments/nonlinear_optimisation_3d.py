"""Nonlinear Optimisation 3D.

Extracted from week4_optimisation_tools.py on 2026-08-12."""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def complex_objective_function(x1, x2, func_type="default"):
    """Create various complex objective functions with multiple peaks and valleys"""
    if func_type == "default":
        # Multi-modal function with peaks and valleys - MODIFIED FOR MINIMIZATION
        return (2 * np.sin(x1) * np.cos(x2) + 
                0.5 * (x1**2 + x2**2) * np.exp(-0.1 * (x1**2 + x2**2)) +
                1.5 * np.sin(0.5 * x1 + 0.3 * x2) +
                0.3 * (x1 - 2)**2 + 0.2 * (x2 + 1)**2)
    elif func_type == "rastrigin":
        # Modified Rastrigin function
        A = 1
        return A * 2 + (x1**2 - A * np.cos(2 * np.pi * x1)) + (x2**2 - A * np.cos(2 * np.pi * x2))
    elif func_type == "himmelblau":
        # Himmelblau's function (modified for better visualization)
        return -((x1**2 + x2 - 11)**2 + (x1 + x2**2 - 7)**2) / 20 + 10
    elif func_type == "rosenbrock":
        # Rosenbrock function (scaled)
        a, b = 1, 10
        return -(b * (x2 - x1**2)**2 + (a - x1)**2) / 100 + 5

def evaluate_constraint(x1, x2, constraint_type, params):
    """Evaluate various constraint types"""
    if constraint_type == "Linear":
        # ax1 + bx2 <= c
        return params['a'] * x1 + params['b'] * x2 - params['c']
    elif constraint_type == "Quadratic":
        # (x1-h)² + (x2-k)² <= r²
        return (x1 - params['h'])**2 + (x2 - params['k'])**2 - params['r']**2
    elif constraint_type == "Polynomial":
        # ax1² + bx1x2 + cx2² + dx1 + ex2 <= f
        return (params['a'] * x1**2 + params['b'] * x1 * x2 + params['c'] * x2**2 + 
                params['d'] * x1 + params['e'] * x2 - params['f'])
    elif constraint_type == "Sine Wave":
        # x2 <= a*sin(b*x1) + c
        return x2 - (params['a'] * np.sin(params['b'] * x1) + params['c'])

def create_3d_optimization_plot(func_type, x_range, y_range, constraints_list, resolution=50):
    """Create 3D surface plot with constraints and feasible region"""
    
    # Create mesh grid
    x1 = np.linspace(x_range[0], x_range[1], resolution)
    x2 = np.linspace(y_range[0], y_range[1], resolution)
    X1, X2 = np.meshgrid(x1, x2)
    
    # Calculate objective function values
    Z = complex_objective_function(X1, X2, func_type)
    
    # Create feasible region mask
    feasible = np.ones_like(X1, dtype=bool)
    
    # Create the plot
    fig = go.Figure()
    
    # Add main objective function surface with reduced opacity
    fig.add_trace(go.Surface(
        x=X1, y=X2, z=Z,
        colorscale='Viridis',
        opacity=0.3,  # Reduced opacity to see constraint surfaces
        name='Objective Function',
        showscale=True,
        colorbar=dict(title="f(x₁, x₂)", x=1.02)
    ))
    
    # Add constraint surfaces
    colors = ['red', 'orange', 'yellow', 'green', 'cyan']  # Different colors for constraints
    for i, constraint in enumerate(constraints_list):
        if constraint['enabled']:
            # Calculate Z values for the constraint surface
            if constraint['type'] == "Linear":
                # For linear constraints: ax₁ + bx₂ = c
                # Rearrange to x₂ = (c - ax₁)/b or x₁ = (c - bx₂)/a
                a, b, c = constraint['params']['a'], constraint['params']['b'], constraint['params']['c']
                if abs(b) > 1e-10:
                    Z_constraint = (c - a * X1) / b
                else:
                    Z_constraint = np.full_like(X1, c / a if abs(a) > 1e-10 else 0)
            
            elif constraint['type'] == "Quadratic":
                # For quadratic constraints: (x₁-h)² + (x₂-k)² = r²
                h, k, r = constraint['params']['h'], constraint['params']['k'], constraint['params']['r']
                Z_constraint = k + np.sqrt(r**2 - (X1 - h)**2)
            
            elif constraint['type'] == "Polynomial":
                # For polynomial constraints
                a, b, c = constraint['params']['a'], constraint['params']['b'], constraint['params']['c']
                d, e, f = constraint['params']['d'], constraint['params']['e'], constraint['params']['f']
                Z_constraint = (f - a * X1**2 - b * X1 * X2 - c * X2**2 - d * X1) / e
            
            elif constraint['type'] == "Sine Wave":
                # For sine wave constraints: x₂ = a*sin(b*x₁) + c
                a, b, c = constraint['params']['a'], constraint['params']['b'], constraint['params']['c']
                Z_constraint = a * np.sin(b * X1) + c
            
            # Add constraint surface
            color = colors[i % len(colors)]
            fig.add_trace(go.Surface(
                x=X1,
                y=X2,
                z=Z[feasible],
                colorscale=[[0, color], [1, color]],
                opacity=0.4,
                name=f'Constraint {i+1}',
                showscale=False
            ))
            
            # Apply constraint to feasible region mask
            constraint_values = evaluate_constraint(X1, X2, constraint['type'], constraint['params'])
            if constraint['inequality'] == '≤':
                feasible &= (constraint_values <= 0)
            else:  # ≥
                feasible &= (constraint_values >= 0)
    
    # Add feasible region surface
    Z_feasible = np.full_like(Z, np.nan)
    Z_feasible[feasible] = Z[feasible]
    fig.add_trace(go.Surface(
        x=X1, y=X2, z=Z_feasible,
        colorscale='Viridis',
        opacity=0.9,
        name='Feasible Region',
        showscale=False
    ))
    
    # Rest of the function remains the same
    # ...existing code for optimal point marking and layout...
    
    # Modify the layout settings
    fig.update_layout(
        width=1000,  # Increased width
        height=800,  # Increased height
        scene=dict(
            camera=dict(
                up=dict(x=0, y=0, z=1),
                center=dict(x=0, y=0, z=0),
                eye=dict(x=1.5, y=1.5, z=1.5)
            ),
            aspectratio=dict(x=1, y=1, z=0.7),
            xaxis=dict(range=[x_range[0], x_range[1]]),
            yaxis=dict(range=[y_range[0], y_range[1]]),
            zaxis=dict(title="f(x₁, x₂)")
        ),
        margin=dict(l=0, r=0, t=30, b=0)  # Reduce margins to maximize plot area
    )
    
    return fig

def render() -> None:
    st.title("3D Nonlinear Optimization with Constraints")
    st.markdown("**Interactive visualization of complex optimization landscapes with multiple constraints**")

    # Create main layout
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🎯 Objective Function Configuration")

        # Function type selection
        func_type = st.selectbox(
            "Select Objective Function Type:",
            ["default", "rastrigin", "himmelblau", "rosenbrock"],
            help="Choose different mathematical functions with various characteristics"
        )

        # Show optimization type
        optimization_type = "MINIMIZE" if func_type == "default" else "MAXIMIZE"
        st.info(f"📊 **Optimization Type:** {optimization_type} f(x₁, x₂)")

        # Plot range controls
        st.markdown("**🔍 Plot Range**")
        col_range1, col_range2 = st.columns(2)

        with col_range1:
            x_min = st.slider("x₁ min", min_value=-10.0, max_value=0.0, value=-5.0, step=0.5)
            x_max = st.slider("x₁ max", min_value=0.0, max_value=10.0, value=5.0, step=0.5)

        with col_range2:
            y_min = st.slider("x₂ min", min_value=-10.0, max_value=0.0, value=-5.0, step=0.5)
            y_max = st.slider("x₂ max", min_value=0.0, max_value=10.0, value=5.0, step=0.5)

        # Resolution control
        resolution = st.slider("Plot Resolution", min_value=30, max_value=100, value=50, 
                              help="Higher resolution = smoother plot but slower rendering")

    with col2:
        st.subheader("🔒 Constraints Configuration")

        # Initialize constraints list
        if 'constraints' not in st.session_state:
            st.session_state.constraints = []

        # Add new constraint
        if st.button("➕ Add Constraint", type="primary"):
            new_constraint = {
                'enabled': True,
                'type': 'Linear',
                'inequality': '≤',
                'params': {'a': 1.0, 'b': 1.0, 'c': 2.0}
            }
            st.session_state.constraints.append(new_constraint)
            st.rerun()

        # Display and configure constraints
        for i, constraint in enumerate(st.session_state.constraints):
            with st.expander(f"Constraint {i+1}", expanded=True):

                # Enable/disable constraint
                constraint['enabled'] = st.checkbox(f"Enable Constraint {i+1}", 
                                                  value=constraint['enabled'], 
                                                  key=f"enable_{i}")

                if constraint['enabled']:
                    # Constraint type
                    constraint['type'] = st.selectbox(
                        "Type:", 
                        ["Linear", "Quadratic", "Polynomial", "Sine Wave"],
                        index=["Linear", "Quadratic", "Polynomial", "Sine Wave"].index(constraint['type']),
                        key=f"type_{i}"
                    )

                    # Inequality direction
                    constraint['inequality'] = st.selectbox(
                        "Inequality:", 
                        ["≤", "≥"],
                        index=0 if constraint['inequality'] == '≤' else 1,
                        key=f"ineq_{i}"
                    )

                    # Parameters based on constraint type
                    if constraint['type'] == "Linear":
                        # ax₁ + bx₂ ≤ c
                        st.markdown("**ax₁ + bx₂ ≤ c**")
                        constraint['params']['a'] = st.slider(f"a", -5.0, 5.0, 
                                                            constraint['params'].get('a', 1.0), 
                                                            0.1, key=f"a_{i}")
                        constraint['params']['b'] = st.slider(f"b", -5.0, 5.0, 
                                                            constraint['params'].get('b', 1.0), 
                                                            0.1, key=f"b_{i}")
                        constraint['params']['c'] = st.slider(f"c", -10.0, 10.0, 
                                                            constraint['params'].get('c', 2.0), 
                                                            0.1, key=f"c_{i}")

                    elif constraint['type'] == "Quadratic":
                        # (x₁-h)² + (x₂-k)² ≤ r²
                        st.markdown("**(x₁-h)² + (x₂-k)² ≤ r²**")
                        constraint['params']['h'] = st.slider(f"h (center x₁)", -5.0, 5.0, 
                                                            constraint['params'].get('h', 0.0), 
                                                            0.1, key=f"h_{i}")
                        constraint['params']['k'] = st.slider(f"k (center x₂)", -5.0, 5.0, 
                                                            constraint['params'].get('k', 0.0), 
                                                            0.1, key=f"k_{i}")
                        constraint['params']['r'] = st.slider(f"r (radius)", 0.5, 5.0, 
                                                            constraint['params'].get('r', 2.0), 
                                                            0.1, key=f"r_{i}")

                    elif constraint['type'] == "Polynomial":
                        # ax₁² + bx₁x₂ + cx₂² + dx₁ + ex₂ ≤ f
                        st.markdown("**ax₁² + bx₁x₂ + cx₂² + dx₁ + ex₂ ≤ f**")
                        constraint['params']['a'] = st.slider(f"a (x₁²)", -2.0, 2.0, 
                                                            constraint['params'].get('a', 1.0), 
                                                            0.1, key=f"poly_a_{i}")
                        constraint['params']['b'] = st.slider(f"b (x₁x₂)", -2.0, 2.0, 
                                                            constraint['params'].get('b', 0.0), 
                                                            0.1, key=f"poly_b_{i}")
                        constraint['params']['c'] = st.slider(f"c (x₂²)", -2.0, 2.0, 
                                                            constraint['params'].get('c', 1.0), 
                                                            0.1, key=f"poly_c_{i}")
                        constraint['params']['d'] = st.slider(f"d (x₁)", -2.0, 2.0, 
                                                            constraint['params'].get('d', 0.0), 
                                                            0.1, key=f"poly_d_{i}")
                        constraint['params']['e'] = st.slider(f"e (x₂)", -2.0, 2.0, 
                                                            constraint['params'].get('e', 0.0), 
                                                            0.1, key=f"poly_e_{i}")
                        constraint['params']['f'] = st.slider(f"f", 0.0, 10.0, 
                                                            constraint['params'].get('f', 5.0), 
                                                            0.1, key=f"poly_f_{i}")

                    elif constraint['type'] == "Sine Wave":
                        # x₂ ≤ a*sin(b*x₁) + c
                        st.markdown("**x₂ ≤ a⋅sin(b⋅x₁) + c**")
                        constraint['params']['a'] = st.slider(f"a (amplitude)", 0.1, 3.0, 
                                                            constraint['params'].get('a', 1.0), 
                                                            0.1, key=f"sin_a_{i}")
                        constraint['params']['b'] = st.slider(f"b (frequency)", 0.1, 2.0, 
                                                            constraint['params'].get('b', 1.0), 
                                                            0.1, key=f"sin_b_{i}")
                        constraint['params']['c'] = st.slider(f"c (offset)", -3.0, 3.0, 
                                                            constraint['params'].get('c', 0.0), 
                                                            0.1, key=f"sin_c_{i}")

                # Remove constraint button
                if st.button(f"🗑️ Remove Constraint {i+1}", key=f"remove_{i}"):
                    st.session_state.constraints.pop(i)
                    st.rerun()

    # Clear all constraints
    if st.session_state.constraints and st.button("🗑️ Clear All Constraints"):
        st.session_state.constraints = []
        st.rerun()

    # Create and display the 3D plot
    st.subheader("📊 3D Optimization Landscape")

    try:
        fig = create_3d_optimization_plot(
            func_type, 
            (x_min, x_max), 
            (y_min, y_max), 
            st.session_state.constraints,
            resolution
        )
        st.plotly_chart(fig, use_container_width=True, config={
            'scrollZoom': True,  # Enable scroll to zoom
            'displayModeBar': True,  # Always show the mode bar
            'modeBarButtonsToAdd': ['drawclosedpath', 'eraseshape'],  # Add drawing tools
            'displaylogo': False  # Remove plotly logo
        })
    except Exception as e:
        st.error(f"Error generating plot: {str(e)}")
        st.info("Try adjusting the parameters or removing some constraints.")

    # Educational content
    with st.expander("📚 Educational Content"):
        st.markdown("""
        ### 3D Nonlinear Optimization Concepts

        **🎯 Learning Objectives:**
        - Understand complex optimization landscapes with multiple local optima
        - Visualize how nonlinear constraints affect the feasible region
        - Explore the relationship between objective functions and constraint boundaries
        - Identify global vs local optima in constrained problems
        - Distinguish between minimization and maximization problems

        **📊 Key Concepts:**

        **🔹 Complex Objective Functions:**
        - **Multi-modal**: Functions with multiple peaks and valleys
        - **Non-convex**: Functions that may have local optima that are not global
        - **Smooth vs Rough**: Different mathematical characteristics affect optimization difficulty
        - **Minimization vs Maximization**: The "default" function demonstrates minimization problems

        **🔹 Constraint Types:**
        - **Linear**: Create flat boundary planes
        - **Quadratic**: Create circular or elliptical boundaries
        - **Polynomial**: Create complex curved boundaries
        - **Trigonometric**: Create periodic or wave-like boundaries

        **🔹 Feasible Region Visualization:**
        - **Colored Surface**: Only the feasible region shows the objective function values
        - **Red Points**: Additional points highlighting the feasible region
        - **Constraint Boundaries**: Orange surfaces showing where constraints are active
        - The global optimum must lie within the feasible (colored) region

        **🔹 Global vs Local Optima:**
        - **Global Optimum** (Gold Diamond): Best solution across entire feasible region
        - **Local Optima**: Best solution in a neighborhood (may exist but not shown)
        - **Minimization Problems**: Look for the lowest point in the feasible region
        - **Maximization Problems**: Look for the highest point in the feasible region

        **🔹 Constraint Activity:**
        - **Active Constraints**: Constraints that are exactly satisfied at the optimum
        - **Inactive Constraints**: Constraints that are not limiting the solution
        - Understanding which constraints are active helps in economic interpretation

        **🔄 Interactive Learning:**
        - Try different function types to see various optimization landscapes
        - Add/remove constraints to see how the feasible region changes
        - Observe how the global optimum location shifts with different constraints
        - Experiment with constraint parameters to understand their geometric meaning
        - Notice how only the feasible region is colored, making it easier to identify valid solutions

        **⚡ Power Systems Applications:**
        This visualization demonstrates concepts relevant to:
        - **Economic Dispatch**: Minimizing total generation cost (minimization problem)
        - **Optimal Power Flow**: Complex feasible regions due to power flow constraints
        - **Unit Commitment**: Discrete decisions creating non-convex problems
        - **Renewable Integration**: Stochastic and time-varying constraints
        - **Cost Optimization**: Most power system optimization problems are minimization problems
        """)
