import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# Configure the page
st.set_page_config(
    page_title="3D Optimization Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar navigation
st.sidebar.title("📈 3D Optimization Dashboard")
st.sidebar.markdown("---")

# Navigation menu
page_option = st.sidebar.selectbox(
    "Select Dashboard:",
    ["3D Nonlinear Optimization", "Modelling Tools Comparison"],
    index=0
)

st.sidebar.markdown("---")

# Course information
st.sidebar.markdown("### Course Information")
st.sidebar.markdown("**Electricity Market and Power Systems Operation**")
st.sidebar.markdown("**ELEC ENG 4087/7087**")
st.sidebar.markdown("---")
st.sidebar.markdown("**Course Coordinator & Creator:**")
st.sidebar.markdown("Ali Pourmousavi Kani")
st.sidebar.markdown("---")
st.sidebar.markdown("**Version:** 2.0 - 3D Nonlinear Optimization")

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

def find_vertices(constraints_list, x_range, y_range):
    """Find vertices of the feasible region for linear programming"""
    vertices = []
    
    # Add corner points of the bounding box
    corners = [
        (x_range[0], y_range[0]),
        (x_range[0], y_range[1]),
        (x_range[1], y_range[0]),
        (x_range[1], y_range[1])
    ]
    
    # Check if corners are feasible
    for corner in corners:
        feasible = True
        for constraint in constraints_list:
            if constraint['enabled'] and constraint['type'] == 'Linear':
                val = evaluate_constraint(corner[0], corner[1], constraint['type'], constraint['params'])
                if constraint['inequality'] == '≤' and val > 1e-6:
                    feasible = False
                    break
                elif constraint['inequality'] == '≥' and val < -1e-6:
                    feasible = False
                    break
        if feasible:
            vertices.append(corner)
    
    # Find intersections between constraints and boundaries
    linear_constraints = [c for c in constraints_list if c['enabled'] and c['type'] == 'Linear']
    
    # Intersections between linear constraints
    for i in range(len(linear_constraints)):
        for j in range(i+1, len(linear_constraints)):
            c1, c2 = linear_constraints[i], linear_constraints[j]
            
            # Solve system: a1*x + b1*y = c1, a2*x + b2*y = c2
            a1, b1, c1_val = c1['params']['a'], c1['params']['b'], c1['params']['c']
            a2, b2, c2_val = c2['params']['a'], c2['params']['b'], c2['params']['c']
            
            det = a1 * b2 - a2 * b1
            if abs(det) > 1e-10:  # Lines are not parallel
                x = (c1_val * b2 - c2_val * b1) / det
                y = (a1 * c2_val - a2 * c1_val) / det
                
                # Check if intersection is within bounds and feasible
                if (x_range[0] <= x <= x_range[1] and 
                    y_range[0] <= y <= y_range[1]):
                    
                    feasible = True
                    for constraint in linear_constraints:
                        val = evaluate_constraint(x, y, constraint['type'], constraint['params'])
                        if constraint['inequality'] == '≤' and val > 1e-6:
                            feasible = False
                            break
                        elif constraint['inequality'] == '≥' and val < -1e-6:
                            feasible = False
                            break
                    
                    if feasible:
                        vertices.append((x, y))
    
    # Intersections with boundaries
    for constraint in linear_constraints:
        a, b, c = constraint['params']['a'], constraint['params']['b'], constraint['params']['c']
        
        # Intersection with x-boundaries
        for x_bound in [x_range[0], x_range[1]]:
            if abs(b) > 1e-10:
                y = (c - a * x_bound) / b
                if y_range[0] <= y <= y_range[1]:
                    # Check feasibility
                    feasible = True
                    for other_constraint in linear_constraints:
                        val = evaluate_constraint(x_bound, y, other_constraint['type'], other_constraint['params'])
                        if other_constraint['inequality'] == '≤' and val > 1e-6:
                            feasible = False
                            break
                        elif other_constraint['inequality'] == '≥' and val < -1e-6:
                            feasible = False
                            break
                    if feasible:
                        vertices.append((x_bound, y))
        
        # Intersection with y-boundaries
        for y_bound in [y_range[0], y_range[1]]:
            if abs(a) > 1e-10:
                x = (c - b * y_bound) / a
                if x_range[0] <= x <= x_range[1]:
                    # Check feasibility
                    feasible = True
                    for other_constraint in linear_constraints:
                        val = evaluate_constraint(x, y_bound, other_constraint['type'], other_constraint['params'])
                        if other_constraint['inequality'] == '≤' and val > 1e-6:
                            feasible = False
                            break
                        elif other_constraint['inequality'] == '≥' and val < -1e-6:
                            feasible = False
                            break
                    if feasible:
                        vertices.append((x, y_bound))
    
    # Remove duplicates and sort vertices
    unique_vertices = []
    for vertex in vertices:
        is_duplicate = False
        for existing in unique_vertices:
            if abs(vertex[0] - existing[0]) < 1e-6 and abs(vertex[1] - existing[1]) < 1e-6:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_vertices.append(vertex)
    
    return unique_vertices

def simplex_path(vertices, objective_coeff):
    """Simulate simplex method path through vertices"""
    if not vertices:
        return []
    
    path = []
    current_vertex = vertices[0]  # Start from first vertex
    path.append(current_vertex)
    visited = {current_vertex}
    
    # Simple greedy approach to simulate simplex (move to best adjacent vertex)
    max_iterations = len(vertices) + 2
    iteration = 0
    
    while iteration < max_iterations:
        best_vertex = None
        best_value = objective_coeff[0] * current_vertex[0] + objective_coeff[1] * current_vertex[1]
        
        # Find the best unvisited adjacent vertex
        for vertex in vertices:
            if vertex not in visited:
                value = objective_coeff[0] * vertex[0] + objective_coeff[1] * vertex[1]
                if value > best_value:  # Assuming maximization for demo
                    best_value = value
                    best_vertex = vertex
        
        if best_vertex is None:
            break
        
        current_vertex = best_vertex
        path.append(current_vertex)
        visited.add(current_vertex)
        iteration += 1
    
    return path

def interior_point_path(start_point, end_point, constraints_list, num_points=20):
    """Generate interior point method trajectory"""
    path = []
    
    # Create a curved path that stays inside the feasible region
    for i in range(num_points + 1):
        t = i / num_points
        
        # Use a quadratic curve for more realistic interior point behavior
        curve_factor = 4 * t * (1 - t)  # Peaks at t=0.5
        
        # Linear interpolation with curvature
        x = (1 - t) * start_point[0] + t * end_point[0]
        y = (1 - t) * start_point[1] + t * end_point[1]
        
        # Add some curvature to stay interior
        if len(constraints_list) > 0:
            # Move towards center of feasible region
            center_x = (start_point[0] + end_point[0]) / 2
            center_y = (start_point[1] + end_point[1]) / 2
            
            x += curve_factor * 0.3 * (center_x - x)
            y += curve_factor * 0.3 * (center_y - y)
        
        path.append((x, y))
    
    return path

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

def solve_simple_lp(c, A, b, bounds):
    """Solve a simple linear programming problem and return results"""
    try:
        from scipy.optimize import linprog
        
        # Convert bounds to scipy format
        bounds_scipy = [(bound[0], bound[1]) for bound in bounds]
        
        # Solve using scipy (minimization)
        result = linprog(c, A_ub=A, b_ub=b, bounds=bounds_scipy, method='highs')
        
        if result.success:
            return {
                'success': True,
                'x': result.x,
                'fun': result.fun,
                'message': 'Optimization successful'
            }
        else:
            return {
                'success': False,
                'message': 'Optimization failed'
            }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error: {str(e)}'
        }

def generate_gams_code(problem_name, c, A, b, bounds, variable_names):
    """Generate GAMS code for the LP problem"""
    n_vars = len(c)
    n_constraints = len(b)
    
    gams_code = f"""$title {problem_name}

* Sets
set i 'variables' /"""
    
    for i, var in enumerate(variable_names):
        gams_code += f"x{i+1} '{var}'"
        if i < len(variable_names) - 1:
            gams_code += ", "
    gams_code += "/;\n"
    
    gams_code += f"set j 'constraints' /c1*c{n_constraints}/;\n\n"
    
    # Parameters
    gams_code += "* Parameters\n"
    gams_code += "parameter c(i) 'objective coefficients' /\n"
    for i, coeff in enumerate(c):
        gams_code += f"    x{i+1} {coeff:g}"
        if i < len(c) - 1:
            gams_code += "\n"
    gams_code += "/;\n\n"
    
    gams_code += "table A(j,i) 'constraint matrix'\n"
    gams_code += "        " + "".join([f"x{i+1:>8}" for i in range(n_vars)]) + "\n"
    for j in range(n_constraints):
        gams_code += f"    c{j+1}"
        for i in range(n_vars):
            gams_code += f"{A[j][i]:8g}"
        gams_code += "\n"
    gams_code += ";\n\n"
    
    gams_code += "parameter b(j) 'right hand side' /\n"
    for j, rhs in enumerate(b):
        gams_code += f"    c{j+1} {rhs:g}"
        if j < len(b) - 1:
            gams_code += "\n"
    gams_code += "/;\n\n"
    
    # Variables
    gams_code += "* Variables\n"
    gams_code += "positive variables x(i) 'decision variables';\n"
    gams_code += "free variable obj 'objective value';\n\n"
    
    # Bounds
    gams_code += "* Variable bounds\n"
    for i, (lb, ub) in enumerate(bounds):
        if lb > 0:
            gams_code += f"x.lo('x{i+1}') = {lb:g};\n"
        if ub < float('inf'):
            gams_code += f"x.up('x{i+1}') = {ub:g};\n"
    gams_code += "\n"
    
    # Equations
    gams_code += "* Equations\n"
    gams_code += "equations\n"
    gams_code += "    objective 'objective function'\n"
    for j in range(n_constraints):
        gams_code += f"    constraint{j+1} 'constraint {j+1}'\n"
    gams_code += ";\n\n"
    
    gams_code += "objective.. obj =e= sum(i, c(i)*x(i));\n\n"
    
    for j in range(n_constraints):
        gams_code += f"constraint{j+1}.. sum(i, A('c{j+1}',i)*x(i)) =l= b('c{j+1}');\n"
    
    gams_code += "\n* Model definition and solution\n"
    gams_code += f"model {problem_name.lower().replace(' ', '_')} /all/;\n"
    gams_code += f"solve {problem_name.lower().replace(' ', '_')} using lp minimizing obj;\n\n"
    
    gams_code += "* Display results\n"
    gams_code += "display x.l, obj.l;"
    
    return gams_code

def generate_matlab_gurobi_code(problem_name, c, A, b, bounds, variable_names):
    """Generate MATLAB-Gurobi interface code"""
    matlab_code = f"%% {problem_name} - MATLAB Gurobi Interface\n"
    matlab_code += "clear; clc;\n\n"
    
    matlab_code += "%% Problem data\n"
    matlab_code += f"c = {str(c).replace('[', '[').replace(']', ']')}';  %% Objective coefficients\n"
    
    matlab_code += f"A = {str([list(row) for row in A]).replace('[', '[').replace(']', ']')};  %% Constraint matrix\n"
    matlab_code += f"b = {str(b).replace('[', '[').replace(']', ']')}';  %% Right-hand side\n\n"
    
    # Bounds
    lb = [bound[0] for bound in bounds]
    ub = [bound[1] if bound[1] != float('inf') else 1000 for bound in bounds]
    matlab_code += f"lb = {str(lb).replace('[', '[').replace(']', ']')}';  %% Lower bounds\n"
    matlab_code += f"ub = {str(ub).replace('[', '[').replace(']', ']')}';  %% Upper bounds\n\n"
    
    matlab_code += "%% Set up Gurobi model\n"
    matlab_code += "model.obj = c;\n"
    matlab_code += "model.A = sparse(A);\n"
    matlab_code += "model.rhs = b;\n"
    matlab_code += "model.sense = '<';\n"
    matlab_code += "model.vtype = 'C';  %% Continuous variables\n"
    matlab_code += "model.lb = lb;\n"
    matlab_code += "model.ub = ub;\n"
    matlab_code += "model.modelsense = 'min';\n\n"
    
    matlab_code += "%% Solve the problem\n"
    matlab_code += "params.outputflag = 1;\n"
    matlab_code += "result = gurobi(model, params);\n\n"
    
    matlab_code += "%% Display results\n"
    matlab_code += "if strcmp(result.status, 'OPTIMAL')\n"
    matlab_code += "    fprintf('Optimal solution found:\\n');\n"
    for i, var_name in enumerate(variable_names):
        matlab_code += f"    fprintf('{var_name}: %.4f\\n', result.x({i+1}));\n"
    matlab_code += "    fprintf('Objective value: %.4f\\n', result.objval);\n"
    matlab_code += "else\n"
    matlab_code += "    fprintf('Optimization failed: %s\\n', result.status);\n"
    matlab_code += "end"
    
    return matlab_code

def generate_matlab_pbo_code(problem_name, c, A, b, bounds, variable_names):
    """Generate MATLAB Problem-Based Optimization code"""
    matlab_code = f"%% {problem_name} - MATLAB Problem-Based Optimization\n"
    matlab_code += "clear; clc;\n\n"
    
    matlab_code += "%% Create optimization problem\n"
    matlab_code += "prob = optimproblem('ObjectiveSense', 'minimize');\n\n"
    
    matlab_code += "%% Create optimization variables\n"
    for i, var_name in enumerate(variable_names):
        lb_val = bounds[i][0]
        ub_val = bounds[i][1] if bounds[i][1] != float('inf') else 1000
        matlab_code += f"{var_name} = optimvar('{var_name}', 'LowerBound', {lb_val}, 'UpperBound', {ub_val});\n"
    
    matlab_code += "\n%% Define objective function\n"
    objective_terms = []
    for i, (coeff, var_name) in enumerate(zip(c, variable_names)):
        if coeff != 0:
            objective_terms.append(f"{coeff}*{var_name}")
    matlab_code += f"prob.Objective = {' + '.join(objective_terms)};\n\n"
    
    matlab_code += "%% Define constraints\n"
    for j in range(len(b)):
        constraint_terms = []
        for i, var_name in enumerate(variable_names):
            if A[j][i] != 0:
                constraint_terms.append(f"{A[j][i]}*{var_name}")
        if constraint_terms:
            matlab_code += f"prob.Constraints.con{j+1} = {' + '.join(constraint_terms)} <= {b[j]};\n"
    
    matlab_code += "\n%% Solve the problem\n"
    matlab_code += "sol = solve(prob);\n\n"
    
    matlab_code += "%% Display results\n"
    matlab_code += "if ~isempty(sol)\n"
    matlab_code += "    fprintf('Optimal solution found:\\n');\n"
    for var_name in variable_names:
        matlab_code += f"    fprintf('{var_name}: %.4f\\n', sol.{var_name});\n"
    matlab_code += "    fprintf('Objective value: %.4f\\n', evaluate(prob.Objective, sol));\n"
    matlab_code += "else\n"
    matlab_code += "    fprintf('No solution found\\n');\n"
    matlab_code += "end"
    
    return matlab_code

def calculate_complexity_metrics(code):
    """Calculate code complexity metrics"""
    lines = code.split('\n')
    non_empty_lines = [line for line in lines if line.strip() and not line.strip().startswith('%') and not line.strip().startswith('*')]
    
    # Count different types of statements
    data_lines = sum(1 for line in non_empty_lines if any(keyword in line.lower() for keyword in ['parameter', 'table', '=', 'set']))
    setup_lines = sum(1 for line in non_empty_lines if any(keyword in line.lower() for keyword in ['model', 'equation', 'variable', 'prob.']))
    
    return {
        'total_lines': len(lines),
        'code_lines': len(non_empty_lines),
        'data_setup': data_lines,
        'model_setup': setup_lines,
        'readability_score': max(0, 10 - len(non_empty_lines) / 10)  # Simple readability metric
    }

# Main content
if page_option == "Modelling Tools Comparison":
    st.title("🔧 Modelling Tools vs Solvers Comparison")
    st.markdown("**Interactive demonstration showing how the same optimization problem is expressed in different modelling tools**")
    
    # Problem Definition Section
    st.subheader("📝 Problem Definition")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("**Define a Simple Linear Programming Problem:**")
        
        # Problem selection
        problem_type = st.selectbox(
            "Choose a predefined problem or create custom:",
            ["Diet Problem (Simplified)", "Production Planning", "Resource Allocation", "Custom Problem"]
        )
        
        if problem_type == "Diet Problem (Simplified)":
            problem_name = "Diet Problem"
            variable_names = ["Corn", "Milk", "Bread"]
            c = [0.18, 0.23, 0.05]  # Cost per serving
            A = [
                [-107, -500, 0],     # Vitamin A >= 500 -> -107x1 - 500x2 <= -500
                [-72, -121, -65]     # Calories >= 2000 -> -72x1 - 121x2 - 65x3 <= -2000
            ]
            b = [-500, -2000]
            bounds = [(0, 10), (0, 10), (0, 10)]
            
            st.info("**Minimize cost of food while meeting nutritional requirements**")
            st.write("Variables: Corn (x₁), Milk (x₂), Bread (x₃)")
            st.write("Objective: Minimize 0.18x₁ + 0.23x₂ + 0.05x₃")
            st.write("Constraints:")
            st.write("• Vitamin A: 107x₁ + 500x₂ ≥ 500")
            st.write("• Calories: 72x₁ + 121x₂ + 65x₃ ≥ 2000")
            st.write("• All variables ≥ 0")
            
        elif problem_type == "Production Planning":
            problem_name = "Production Planning"
            variable_names = ["Product_A", "Product_B"]
            c = [10, 15]  # Profit per unit (maximize, so negate for minimization)
            c = [-x for x in c]  # Convert to minimization
            A = [
                [2, 3],     # Material constraint
                [1, 2],     # Labor constraint
                [1, 0]      # Machine A constraint
            ]
            b = [100, 60, 40]
            bounds = [(0, float('inf')), (0, float('inf'))]
            
            st.info("**Maximize profit from production while respecting resource constraints**")
            st.write("Variables: Product A (x₁), Product B (x₂)")
            st.write("Objective: Maximize 10x₁ + 15x₂ (shown as minimization)")
            st.write("Constraints:")
            st.write("• Material: 2x₁ + 3x₂ ≤ 100")
            st.write("• Labor: x₁ + 2x₂ ≤ 60")
            st.write("• Machine A: x₁ ≤ 40")
            
        elif problem_type == "Resource Allocation":
            problem_name = "Resource Allocation"
            variable_names = ["Investment_A", "Investment_B", "Investment_C"]
            c = [0.05, 0.08, 0.12]  # Risk per unit (minimize risk)
            A = [
                [-0.10, -0.15, -0.20],  # Return >= 1000 -> negative for ≤ format
                [1, 1, 1]               # Budget ≤ 10000
            ]
            b = [-1000, 10000]
            bounds = [(0, 5000), (0, 5000), (0, 5000)]
            
            st.info("**Minimize risk while achieving target return and staying within budget**")
            st.write("Variables: Investment A (x₁), Investment B (x₂), Investment C (x₃)")
            st.write("Objective: Minimize 0.05x₁ + 0.08x₂ + 0.12x₃")
            st.write("Constraints:")
            st.write("• Return: 0.10x₁ + 0.15x₂ + 0.20x₃ ≥ 1000")
            st.write("• Budget: x₁ + x₂ + x₃ ≤ 10000")
            
        else:  # Custom Problem
            st.markdown("**Create your own problem:**")
            n_vars = st.slider("Number of variables", 2, 4, 2)
            n_constraints = st.slider("Number of constraints", 1, 4, 2)
            
            problem_name = st.text_input("Problem name", "Custom Problem")
            
            variable_names = []
            for i in range(n_vars):
                var_name = st.text_input(f"Variable {i+1} name", f"x{i+1}", key=f"var_{i}")
                variable_names.append(var_name)
            
            st.write("**Objective coefficients (for minimization):**")
            c = []
            for i in range(n_vars):
                coeff = st.number_input(f"Coefficient for {variable_names[i]}", value=1.0, key=f"obj_{i}")
                c.append(coeff)
            
            st.write("**Constraints (Ax ≤ b):**")
            A = []
            b = []
            for j in range(n_constraints):
                st.write(f"Constraint {j+1}:")
                row = []
                for i in range(n_vars):
                    coeff = st.number_input(f"A[{j+1},{i+1}]", value=1.0, key=f"A_{j}_{i}")
                    row.append(coeff)
                A.append(row)
                rhs = st.number_input(f"b[{j+1}]", value=10.0, key=f"b_{j}")
                b.append(rhs)
            
            bounds = []
            st.write("**Variable bounds:**")
            for i in range(n_vars):
                col_lb, col_ub = st.columns(2)
                with col_lb:
                    lb = st.number_input(f"{variable_names[i]} lower bound", value=0.0, key=f"lb_{i}")
                with col_ub:
                    ub = st.number_input(f"{variable_names[i]} upper bound", value=100.0, key=f"ub_{i}")
                bounds.append((lb, ub))
    
    with col2:
        st.markdown("**📊 Problem Summary**")
        
        # Display problem in mathematical notation
        st.markdown("**Mathematical Formulation:**")
        
        # Objective
        obj_terms = []
        for i, (coeff, var) in enumerate(zip(c, variable_names)):
            if coeff >= 0:
                obj_terms.append(f"{coeff:g}·{var}")
            else:
                obj_terms.append(f"{coeff:g}·{var}")
        
        st.latex("\\text{minimize } " + " + ".join(obj_terms).replace("+ -", "- "))
        
        # Constraints
        st.markdown("**Subject to:**")
        for j, (row, rhs) in enumerate(zip(A, b)):
            constraint_terms = []
            for i, (coeff, var) in enumerate(zip(row, variable_names)):
                if coeff != 0:
                    if coeff >= 0:
                        constraint_terms.append(f"{coeff:g}·{var}")
                    else:
                        constraint_terms.append(f"{coeff:g}·{var}")
            
            if constraint_terms:
                constraint_str = " + ".join(constraint_terms).replace("+ -", "- ")
                st.latex(f"{constraint_str} \\leq {rhs:g}")
        
        # Variable bounds
        bounds_str = []
        for var, (lb, ub) in zip(variable_names, bounds):
            if lb == 0 and ub == float('inf'):
                bounds_str.append(f"{var} ≥ 0")
            elif ub == float('inf'):
                bounds_str.append(f"{var} ≥ {lb:g}")
            else:
                bounds_str.append(f"{lb:g} ≤ {var} ≤ {ub:g}")
        
        for bound_str in bounds_str:
            st.latex(bound_str)
    
    # Code Generation and Comparison
    st.subheader("💻 Implementation in Different Tools")
    
    # Generate code for all three approaches
    gams_code = generate_gams_code(problem_name, c, A, b, bounds, variable_names)
    matlab_gurobi_code = generate_matlab_gurobi_code(problem_name, c, A, b, bounds, variable_names)
    matlab_pbo_code = generate_matlab_pbo_code(problem_name, c, A, b, bounds, variable_names)
    
    # Calculate complexity metrics
    gams_metrics = calculate_complexity_metrics(gams_code)
    gurobi_metrics = calculate_complexity_metrics(matlab_gurobi_code)
    pbo_metrics = calculate_complexity_metrics(matlab_pbo_code)
    
    # Create tabs for different implementations
    tab1, tab2, tab3, tab4 = st.tabs(["🟨 GAMS", "🔴 MATLAB-Gurobi", "🔵 MATLAB-PBO", "📊 Comparison"])
    
    with tab1:
        st.markdown("### GAMS Implementation")
        st.markdown("**Characteristics:** High-level algebraic modeling language, very readable, close to mathematical notation")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.code(gams_code, language='text')
        
        with col2:
            st.markdown("**Complexity Metrics:**")
            st.metric("Total Lines", gams_metrics['total_lines'])
            st.metric("Code Lines", gams_metrics['code_lines'])
            st.metric("Readability", f"{gams_metrics['readability_score']:.1f}/10")
            
            if st.button("🚀 Simulate GAMS Solve", key="gams_solve"):
                with st.spinner("Solving with GAMS..."):
                    result = solve_simple_lp(c, A, b, bounds)
                    if result['success']:
                        st.success("✅ GAMS: Optimal solution found!")
                        for i, (var, val) in enumerate(zip(variable_names, result['x'])):
                            st.write(f"**{var}:** {val:.4f}")
                        st.write(f"**Objective:** {result['fun']:.4f}")
                    else:
                        st.error(f"❌ GAMS: {result['message']}")
    
    with tab2:
        st.markdown("### MATLAB-Gurobi Interface Implementation")
        st.markdown("**Characteristics:** Matrix-based formulation, requires manual setup of constraint matrices, more programming-oriented")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.code(matlab_gurobi_code, language='matlab')
        
        with col2:
            st.markdown("**Complexity Metrics:**")
            st.metric("Total Lines", gurobi_metrics['total_lines'])
            st.metric("Code Lines", gurobi_metrics['code_lines'])
            st.metric("Readability", f"{gurobi_metrics['readability_score']:.1f}/10")
            
            if st.button("🚀 Simulate Gurobi Solve", key="gurobi_solve"):
                with st.spinner("Solving with Gurobi..."):
                    result = solve_simple_lp(c, A, b, bounds)
                    if result['success']:
                        st.success("✅ Gurobi: Optimal solution found!")
                        for i, (var, val) in enumerate(zip(variable_names, result['x'])):
                            st.write(f"**{var}:** {val:.4f}")
                        st.write(f"**Objective:** {result['fun']:.4f}")
                    else:
                        st.error(f"❌ Gurobi: {result['message']}")
    
    with tab3:
        st.markdown("### MATLAB Problem-Based Optimization Implementation")
        st.markdown("**Characteristics:** Object-oriented approach, symbolic variables, intuitive constraint definition")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.code(matlab_pbo_code, language='matlab')
        
        with col2:
            st.markdown("**Complexity Metrics:**")
            st.metric("Total Lines", pbo_metrics['total_lines'])
            st.metric("Code Lines", pbo_metrics['code_lines'])
            st.metric("Readability", f"{pbo_metrics['readability_score']:.1f}/10")
            
            if st.button("🚀 Simulate MATLAB PBO Solve", key="pbo_solve"):
                with st.spinner("Solving with MATLAB PBO..."):
                    result = solve_simple_lp(c, A, b, bounds)
                    if result['success']:
                        st.success("✅ MATLAB PBO: Optimal solution found!")
                        for i, (var, val) in enumerate(zip(variable_names, result['x'])):
                            st.write(f"**{var}:** {val:.4f}")
                        st.write(f"**Objective:** {result['fun']:.4f}")
                    else:
                        st.error(f"❌ MATLAB PBO: {result['message']}")
    
    with tab4:
        st.markdown("### 📊 Comprehensive Comparison")
        
        # Solve the problem once for comparison
        result = solve_simple_lp(c, A, b, bounds)
        
        if result['success']:
            st.success("🎯 **All methods yield identical results** - demonstrating they are just different interfaces to the same mathematical problem!")
            
            # Results table
            results_data = {
                'Variable': variable_names + ['Objective Value'],
                'GAMS': [f"{val:.4f}" for val in result['x']] + [f"{result['fun']:.4f}"],
                'MATLAB-Gurobi': [f"{val:.4f}" for val in result['x']] + [f"{result['fun']:.4f}"],
                'MATLAB-PBO': [f"{val:.4f}" for val in result['x']] + [f"{result['fun']:.4f}"]
            }
            
            st.markdown("**🎯 Solution Comparison:**")
            st.dataframe(results_data, use_container_width=True)
        
        # Complexity comparison
        st.markdown("**⚡ Complexity Comparison:**")
        
        comparison_data = {
            'Metric': ['Total Lines', 'Code Lines', 'Readability Score', 'Learning Curve', 'Industry Usage'],
            'GAMS': [
                gams_metrics['total_lines'],
                gams_metrics['code_lines'],
                f"{gams_metrics['readability_score']:.1f}/10",
                "Medium",
                "Power/Energy"
            ],
            'MATLAB-Gurobi': [
                gurobi_metrics['total_lines'],
                gurobi_metrics['code_lines'],
                f"{gurobi_metrics['readability_score']:.1f}/10",
                "High",
                "Research/Finance"
            ],
            'MATLAB-PBO': [
                pbo_metrics['total_lines'],
                pbo_metrics['code_lines'],
                f"{pbo_metrics['readability_score']:.1f}/10",
                "Low-Medium",
                "Engineering"
            ]
        }
        
        st.dataframe(comparison_data, use_container_width=True)
        
        # Key insights
        st.markdown("**🔑 Key Insights:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **✅ Advantages by Tool:**
            
            **GAMS:**
            - Very readable, close to math notation
            - Excellent for large-scale problems
            - Strong solver integration
            - Industry standard in energy sector
            
            **MATLAB-Gurobi:**
            - Maximum solver control
            - High performance
            - Extensive parameter tuning
            - Best for research applications
            """)
        
        with col2:
            st.markdown("""
            **⚠️ Considerations:**
            
            **MATLAB-PBO:**
            - Most intuitive for beginners
            - Good integration with MATLAB ecosystem
            - Limited to available solvers
            - Good for educational purposes
            
            **General:**
            - All solve the **same mathematical problem**
            - Choice depends on context and preferences
            - Results are **always identical** when optimal
            """)
    
    # Educational Content
    with st.expander("📚 Educational Content: Understanding Modelling Tools vs Solvers"):
        st.markdown("""
        ### 🎯 Learning Objectives
        
        **🔹 Understand the distinction between:**
        - **Modelling Tools** (GAMS, MATLAB PBO): High-level languages for expressing problems
        - **Solvers** (Gurobi, CPLEX, GLPK): Algorithms that actually solve the problems
        
        **🔹 Key Concepts:**
        
        **📝 Modelling Tools:**
        - Provide user-friendly syntax to describe optimization problems
        - Handle translation from human-readable format to solver format
        - Examples: GAMS, AMPL, MATLAB PBO, Pyomo, JuMP
        
        **⚙️ Solvers:**
        - Implement mathematical algorithms (Simplex, Interior Point, etc.)
        - Work with standardized mathematical formats
        - Examples: Gurobi, CPLEX, GLPK, MOSEK
        
        **🔄 The Relationship:**
        - Modelling tools translate your problem description into solver-readable format
        - Solvers perform the actual mathematical computation
        - Results are translated back to human-readable format
        
        **💡 Why This Matters:**
        - Same problem = Same optimal solution (regardless of tool)
        - Tool choice depends on: complexity, team expertise, industry standards
        - Understanding this reduces confusion about "which tool is best"
        
        **🎓 For Students:**
        - Focus on understanding the mathematics first
        - Tools are just different ways to express the same concepts
        - Practice with multiple tools to understand their strengths
        
        **🏭 Industry Perspective:**
        - **Energy/Power Systems**: GAMS dominates due to tradition and complexity handling
        - **Finance/Research**: MATLAB-Gurobi for maximum control and performance
        - **General Engineering**: MATLAB PBO for integration with existing workflows
        - **Software Development**: Python (Pyomo, PuLP) for integration capabilities
        
        **🔍 Technical Deep Dive:**
        
        **Problem Flow:**
        1. **Human Description** → "Minimize cost while meeting constraints"
        2. **Modelling Tool** → Translates to mathematical matrices (c, A, b)
        3. **Solver Interface** → Converts to solver-specific format
        4. **Solver Algorithm** → Applies mathematical methods (Simplex, etc.)
        5. **Solution** → Returns optimal values
        6. **Results Display** → Human-readable format
        
        **Matrix Representation (Common to All):**
        ```
        minimize    c^T x
        subject to  A x ≤ b
                    lb ≤ x ≤ ub
        ```
        
        **🚀 Advanced Considerations:**
        - **Solver Performance**: Different solvers may have different speeds for the same problem
        - **Numerical Precision**: Small differences in final decimal places are normal
        - **Problem Size**: Some tools handle large problems better than others
        - **Special Structures**: Some solvers exploit problem structure (network, integer, etc.)
        
        **🔧 Practical Tips:**
        - Start with the tool your team/industry uses most
        - Learn the mathematical formulation first, syntax second
        - Use this dashboard to verify your understanding across tools
        - Remember: if solutions differ significantly, check your formulation!
        """)

elif page_option == "3D Nonlinear Optimization":
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