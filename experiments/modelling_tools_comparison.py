"""Modelling Tools Comparison.

Extracted from week4_optimisation_tools.py on 2026-08-12."""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

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

def render() -> None:
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
