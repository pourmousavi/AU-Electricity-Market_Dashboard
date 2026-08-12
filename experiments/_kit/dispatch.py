"""Shared dispatch page for week 7.

Extracted from week7_ed_viu.py (its module-level body and main(), minus the tab
block at lines 1626-1686) on 2026-08-12. The five dispatch experiments --
generator setup, comparison results, detailed analysis, individual generators
and Pareto frontier -- each render this page plus their own tab body.
"""
from typing import Callable, Optional

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

# Custom CSS
PAGE_CSS = """
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .problem-box {
        background-color: #f0f8ff;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #ddd;
        text-align: center;
    }
</style>
"""

class EDProblem:
    def __init__(self, generators, demand_profile, problem_type):
        self.generators = generators
        self.demand_profile = demand_profile
        self.problem_type = problem_type
        self.solution = None
        self.solution_unconstrained = None  # For ED-2: unconstrained optimization result
        self.solution_ramping_adjusted = None  # For ED-2: ramping-adjusted result
        self.total_cost = None
        self.total_cost_ramping_adjusted = None  # For ED-2: cost after ramping adjustment
        self.emissions = None
        self.emissions_ramping_adjusted = None  # For ED-2: emissions after ramping adjustment
        
    def solve(self):
        """Solve the optimization problem"""
        try:
            if self.problem_type == "ED-2":
                return self._solve_ed2_with_ramping_adjustment()
            else:
                return self._solve_standard()
                
        except Exception as e:
            st.error(f"Solver error for {self.problem_type}: {str(e)}")
            return False
    
    def _solve_ed2_with_ramping_adjustment(self):
        """Solve ED-2: Independent optimization per time period + post-processing ramping adjustment"""
        n_gen = len(self.generators)
        n_time = len(self.demand_profile)
        
        # Step 1: Solve each time period independently (ignoring ramping)
        unconstrained_solution = np.zeros((n_gen, n_time))
        
        for t in range(n_time):
            # Single time period optimization
            P_t = cp.Variable(n_gen, nonneg=True)
            
            # Objective for this time period
            cost_t = 0
            for i, gen in enumerate(self.generators):
                cost_t += gen['a'] * cp.square(P_t[i]) + gen['b'] * P_t[i] + gen['c']
            
            # Constraints for this time period
            constraints_t = [cp.sum(P_t) == self.demand_profile[t]]
            
            # Generator limits
            for i, gen in enumerate(self.generators):
                constraints_t.append(P_t[i] >= gen['pmin'])
                constraints_t.append(P_t[i] <= gen['pmax'])
            
            # Solve for this time period
            problem_t = cp.Problem(cp.Minimize(cost_t), constraints_t)
            problem_t.solve(solver=cp.OSQP, verbose=False)
            
            if problem_t.status != cp.OPTIMAL:
                st.error(f"Failed to solve ED-2 for time period {t+1}")
                return False
            
            unconstrained_solution[:, t] = P_t.value
        
        # Store unconstrained solution
        self.solution_unconstrained = unconstrained_solution.copy()
        
        # Step 2: Apply ramping constraints through post-processing
        ramping_adjusted_solution = self._apply_ramping_adjustment(unconstrained_solution)
        
        # Store both solutions
        self.solution = ramping_adjusted_solution  # Main solution is ramping-adjusted
        self.solution_ramping_adjusted = ramping_adjusted_solution
        
        # Calculate costs and emissions for both solutions
        self.total_cost = self._calculate_total_cost(ramping_adjusted_solution)
        self.emissions = self._calculate_emissions(ramping_adjusted_solution)
        
        return True
    
    def _apply_ramping_adjustment(self, unconstrained_solution):
        """Apply ramping constraints to unconstrained solution through iterative adjustment"""
        n_gen, n_time = unconstrained_solution.shape
        adjusted_solution = unconstrained_solution.copy()
        
        # Start from first time period (no ramping constraint)
        for t in range(1, n_time):
            demand_shortfall = 0
            demand_excess = 0
            
            # Check ramping constraints for each generator
            for i, gen in enumerate(self.generators):
                prev_output = adjusted_solution[i, t-1]
                desired_output = unconstrained_solution[i, t]
                
                # Apply ramp up constraint
                max_ramp_up = prev_output + gen['ramp_up']
                if desired_output > max_ramp_up:
                    demand_shortfall += desired_output - max_ramp_up
                    adjusted_solution[i, t] = max_ramp_up
                
                # Apply ramp down constraint
                max_ramp_down = prev_output - gen['ramp_down']
                if desired_output < max_ramp_down:
                    demand_excess += max_ramp_down - desired_output
                    adjusted_solution[i, t] = max_ramp_down
                else:
                    adjusted_solution[i, t] = desired_output
            
            # Redistribute shortfall to generators with available ramping capacity
            if demand_shortfall > 0:
                self._redistribute_shortfall(adjusted_solution, t, demand_shortfall)
            
            # Redistribute excess generation
            if demand_excess > 0:
                self._redistribute_excess(adjusted_solution, t, demand_excess)
        
        return adjusted_solution
    
    def _redistribute_shortfall(self, solution, t, shortfall):
        """Redistribute demand shortfall to generators with available ramping capacity"""
        available_generators = []
        
        for i, gen in enumerate(self.generators):
            current_output = solution[i, t]
            max_possible = min(
                solution[i, t-1] + gen['ramp_up'],  # Ramping limit
                gen['pmax']  # Capacity limit
            )
            available_capacity = max_possible - current_output
            
            if available_capacity > 0:
                available_generators.append((i, available_capacity))
        
        # Sort by marginal cost (cheapest first)
        available_generators.sort(key=lambda x: self.generators[x[0]]['b'])
        
        # Allocate shortfall to available generators
        remaining_shortfall = shortfall
        for i, available_capacity in available_generators:
            if remaining_shortfall <= 0:
                break
            
            allocation = min(available_capacity, remaining_shortfall)
            solution[i, t] += allocation
            remaining_shortfall -= allocation
    
    def _redistribute_excess(self, solution, t, excess):
        """Redistribute excess generation from generators with ramping constraints"""
        reducible_generators = []
        
        for i, gen in enumerate(self.generators):
            current_output = solution[i, t]
            min_possible = max(
                solution[i, t-1] - gen['ramp_down'],  # Ramping limit
                gen['pmin']  # Minimum capacity
            )
            reducible_capacity = current_output - min_possible
            
            if reducible_capacity > 0:
                reducible_generators.append((i, reducible_capacity))
        
        # Sort by marginal cost (most expensive first)
        reducible_generators.sort(key=lambda x: self.generators[x[0]]['b'], reverse=True)
        
        # Reduce excess from reducible generators
        remaining_excess = excess
        for i, reducible_capacity in reducible_generators:
            if remaining_excess <= 0:
                break
            
            reduction = min(reducible_capacity, remaining_excess)
            solution[i, t] -= reduction
            remaining_excess -= reduction
    
    def _solve_standard(self):
        """Solve standard ED problem (ED-3, ED-4, ED-5) with all constraints in optimization"""
        n_gen = len(self.generators)
        n_time = len(self.demand_profile)
        
        if self.problem_type == "ED-5":
            # Multi-objective optimization: generate Pareto frontier
            return self._solve_ed5_pareto()
        
        # Decision variables: Power output for each generator at each time
        P = cp.Variable((n_gen, n_time), nonneg=True)
        
        # Objective function: minimize total cost
        cost = 0
        for t in range(n_time):
            for i, gen in enumerate(self.generators):
                cost += gen['a'] * cp.square(P[i, t]) + gen['b'] * P[i, t] + gen['c']
        
        # Constraints
        constraints = []
        
        # Power balance for each time period
        for t in range(n_time):
            constraints.append(cp.sum(P[:, t]) == self.demand_profile[t])
        
        # Generator limits
        for i, gen in enumerate(self.generators):
            for t in range(n_time):
                constraints.append(P[i, t] >= gen['pmin'])
                constraints.append(P[i, t] <= gen['pmax'])
        
        # Ramping constraints (ED-3, ED-4, ED-5)
        if self.problem_type in ["ED-3", "ED-4", "ED-5"]:
            for i, gen in enumerate(self.generators):
                for t in range(1, n_time):
                    constraints.append(P[i, t] - P[i, t-1] <= gen['ramp_up'])
                    constraints.append(P[i, t-1] - P[i, t] <= gen['ramp_down'])
        
        # Emission constraints (ED-4, ED-5)
        if self.problem_type in ["ED-4", "ED-5"]:
            total_emissions = 0
            for t in range(n_time):
                for i, gen in enumerate(self.generators):
                    total_emissions += gen['emission_rate'] * P[i, t]
            
            emission_limit = st.session_state.get('emission_limit', 1000)
            constraints.append(total_emissions <= emission_limit)
        
        # Solve the problem
        problem = cp.Problem(cp.Minimize(cost), constraints)
        problem.solve(solver=cp.OSQP, verbose=False)
        
        if problem.status == cp.OPTIMAL:
            self.solution = P.value
            self.total_cost = problem.value
            self.emissions = self._calculate_emissions(self.solution)
            return True
        else:
            st.error(f"Optimization failed for {self.problem_type}: {problem.status}")
            return False
    
    def _solve_ed5_pareto(self):
        """Solve ED-5 with multiple weight combinations to generate Pareto frontier"""
        n_gen = len(self.generators)
        n_time = len(self.demand_profile)
        
        # First, solve pure cost and pure emission problems to get normalization bounds
        cost_bounds = self._get_objective_bounds()
        
        # More comprehensive weight combinations for better Pareto frontier
        weight_combinations = []
        
        # Add corner points
        weight_combinations.append((1.0, 0.0))  # Pure cost
        weight_combinations.append((0.0, 1.0))  # Pure emission
        
        # Add fine-grained intermediate points
        for i in range(1, 20):  # 18 intermediate points
            w_cost = i / 20.0
            w_emission = 1.0 - w_cost
            weight_combinations.append((w_cost, w_emission))
        
        # Add some additional strategic points
        strategic_points = [
            (0.95, 0.05), (0.85, 0.15), (0.75, 0.25), (0.65, 0.35),
            (0.55, 0.45), (0.45, 0.55), (0.35, 0.65), (0.25, 0.75),
            (0.15, 0.85), (0.05, 0.95)
        ]
        weight_combinations.extend(strategic_points)
        
        # Remove duplicates and sort
        weight_combinations = list(set(weight_combinations))
        weight_combinations.sort(key=lambda x: x[0], reverse=True)
        
        pareto_solutions = []
        pareto_costs = []
        pareto_emissions = []
        successful_weights = []
        
        st.info(f"Generating Pareto frontier with {len(weight_combinations)} weight combinations...")
        progress_bar = st.progress(0)
        
        for idx, (w_cost, w_emission) in enumerate(weight_combinations):
            # Update progress
            progress_bar.progress((idx + 1) / len(weight_combinations))
            
            # Decision variables
            P = cp.Variable((n_gen, n_time), nonneg=True)
            
            # Cost objective
            cost_obj = 0
            for t in range(n_time):
                for i, gen in enumerate(self.generators):
                    cost_obj += gen['a'] * cp.square(P[i, t]) + gen['b'] * P[i, t] + gen['c']
            
            # Emission objective
            emission_obj = 0
            for t in range(n_time):
                for i, gen in enumerate(self.generators):
                    emission_obj += gen['emission_rate'] * P[i, t]
            
            # Use proper normalization based on bounds
            cost_range = cost_bounds['max_cost'] - cost_bounds['min_cost']
            emission_range = cost_bounds['max_emission'] - cost_bounds['min_emission']
            
            # Avoid division by zero
            cost_normalization = max(cost_range, 1000)
            emission_normalization = max(emission_range, 100)
            
            # Normalized combined objective
            if w_cost > 0 and w_emission > 0:
                # Weighted sum with proper normalization
                normalized_cost = (cost_obj - cost_bounds['min_cost']) / cost_normalization
                normalized_emission = (emission_obj - cost_bounds['min_emission']) / emission_normalization
                objective = w_cost * normalized_cost + w_emission * normalized_emission
            elif w_cost == 1.0:
                objective = cost_obj
            else:  # w_emission == 1.0
                objective = emission_obj
            
            # Constraints
            constraints = []
            
            # Power balance
            for t in range(n_time):
                constraints.append(cp.sum(P[:, t]) == self.demand_profile[t])
            
            # Generator limits
            for i, gen in enumerate(self.generators):
                for t in range(n_time):
                    constraints.append(P[i, t] >= gen['pmin'])
                    constraints.append(P[i, t] <= gen['pmax'])
            
            # Ramping constraints
            for i, gen in enumerate(self.generators):
                for t in range(1, n_time):
                    constraints.append(P[i, t] - P[i, t-1] <= gen['ramp_up'])
                    constraints.append(P[i, t-1] - P[i, t] <= gen['ramp_down'])
            
            # Solve with different solvers as backup
            problem = cp.Problem(cp.Minimize(objective), constraints)
            
            # Try multiple solvers
            solvers_to_try = [cp.OSQP, cp.ECOS, cp.SCS]
            solved = False
            
            for solver in solvers_to_try:
                try:
                    problem.solve(solver=solver, verbose=False, max_iters=10000)
                    if problem.status == cp.OPTIMAL:
                        solved = True
                        break
                except:
                    continue
            
            if solved and problem.status == cp.OPTIMAL:
                solution = P.value
                cost = self._calculate_total_cost(solution)
                emissions = self._calculate_emissions(solution)
                
                # Check for duplicates (within tolerance)
                is_duplicate = False
                tolerance = 1e-3
                for existing_cost, existing_emission in zip(pareto_costs, pareto_emissions):
                    if (abs(cost - existing_cost) < tolerance * abs(existing_cost) and 
                        abs(emissions - existing_emission) < tolerance * abs(existing_emission)):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    pareto_solutions.append(solution)
                    pareto_costs.append(cost)
                    pareto_emissions.append(emissions)
                    successful_weights.append((w_cost, w_emission))
        
        # Clear progress bar
        progress_bar.empty()
        
        if len(pareto_solutions) < 5:
            st.warning(f"Only {len(pareto_solutions)} unique Pareto points found. Trying alternative approach...")
            return self._solve_ed5_epsilon_constraint()
        
        # Filter for truly Pareto optimal points
        pareto_indices = self._filter_pareto_optimal(pareto_costs, pareto_emissions)
        
        if pareto_indices:
            # Keep only Pareto optimal solutions
            filtered_solutions = [pareto_solutions[i] for i in pareto_indices]
            filtered_costs = [pareto_costs[i] for i in pareto_indices]
            filtered_emissions = [pareto_emissions[i] for i in pareto_indices]
            filtered_weights = [successful_weights[i] for i in pareto_indices]
            
            # Sort by cost for better visualization
            sorted_data = sorted(zip(filtered_costs, filtered_emissions, filtered_solutions, filtered_weights))
            filtered_costs, filtered_emissions, filtered_solutions, filtered_weights = zip(*sorted_data)
            
            # Store the middle solution as the main solution
            middle_idx = len(filtered_solutions) // 2
            self.solution = filtered_solutions[middle_idx]
            self.total_cost = filtered_costs[middle_idx]
            self.emissions = filtered_emissions[middle_idx]
            
            # Store Pareto frontier data
            self.pareto_costs = list(filtered_costs)
            self.pareto_emissions = list(filtered_emissions)
            self.pareto_solutions = list(filtered_solutions)
            self.weight_combinations = list(filtered_weights);
            
            st.success(f"Generated Pareto frontier with {len(filtered_costs)} optimal points!")
            return True
        else:
            st.error("No Pareto optimal solutions found!")
            return False
    
    def _get_objective_bounds(self):
        """Get bounds for cost and emission objectives for normalization"""
        n_gen = len(self.generators)
        n_time = len(self.demand_profile)
        
        bounds = {}
        
        # Solve for minimum cost (ignore emissions)
        P_cost = cp.Variable((n_gen, n_time), nonneg=True)
        cost_obj = 0
        for t in range(n_time):
            for i, gen in enumerate(self.generators):
                cost_obj += gen['a'] * cp.square(P_cost[i, t]) + gen['b'] * P_cost[i, t] + gen['c']
        
        constraints_cost = []
        for t in range(n_time):
            constraints_cost.append(cp.sum(P_cost[:, t]) == self.demand_profile[t])
        
        for i, gen in enumerate(self.generators):
            for t in range(n_time):
                constraints_cost.append(P_cost[i, t] >= gen['pmin'])
                constraints_cost.append(P_cost[i, t] <= gen['pmax'])
        
        for i, gen in enumerate(self.generators):
            for t in range(1, n_time):
                constraints_cost.append(P_cost[i, t] - P_cost[i, t-1] <= gen['ramp_up'])
                constraints_cost.append(P_cost[i, t-1] - P_cost[i, t] <= gen['ramp_down'])
        
        prob_cost = cp.Problem(cp.Minimize(cost_obj), constraints_cost)
        prob_cost.solve(solver=cp.OSQP, verbose=False)
        
        if prob_cost.status == cp.OPTIMAL:
            bounds['min_cost'] = prob_cost.value
            bounds['min_emission'] = self._calculate_emissions(P_cost.value)
        else:
            bounds['min_cost'] = 0
            bounds['min_emission'] = 0
        
        # Solve for minimum emissions (ignore cost)
        P_emission = cp.Variable((n_gen, n_time), nonneg=True)
        emission_obj = 0
        for t in range(n_time):
            for i, gen in enumerate(self.generators):
                emission_obj += gen['emission_rate'] * P_emission[i, t]
        
        constraints_emission = []
        for t in range(n_time):
            constraints_emission.append(cp.sum(P_emission[:, t]) == self.demand_profile[t])
        
        for i, gen in enumerate(self.generators):
            for t in range(n_time):
                constraints_emission.append(P_emission[i, t] >= gen['pmin'])
                constraints_emission.append(P_emission[i, t] <= gen['pmax'])
        
        for i, gen in enumerate(self.generators):
            for t in range(1, n_time):
                constraints_emission.append(P_emission[i, t] - P_emission[i, t-1] <= gen['ramp_up'])
                constraints_emission.append(P_emission[i, t-1] - P_emission[i, t] <= gen['ramp_down'])
        
        prob_emission = cp.Problem(cp.Minimize(emission_obj), constraints_emission)
        prob_emission.solve(solver=cp.OSQP, verbose=False)
        
        if prob_emission.status == cp.OPTIMAL:
            bounds['max_cost'] = self._calculate_total_cost(P_emission.value)
            bounds['max_emission'] = prob_emission.value
        else:
            # Fallback bounds
            bounds['max_cost'] = bounds['min_cost'] * 2
            bounds['max_emission'] = bounds['min_emission'] * 2
        
        return bounds
    
    def _solve_ed5_epsilon_constraint(self):
        """Alternative epsilon-constraint method for generating Pareto frontier"""
        st.info("Using epsilon-constraint method for Pareto frontier generation...")
        
        # Get bounds first
        bounds = self._get_objective_bounds()
        
        # Create emission levels
        n_points = 15
        emission_levels = np.linspace(bounds['min_emission'], bounds['max_emission'], n_points)
        
        pareto_solutions = []
        pareto_costs = []
        pareto_emissions = []
        
        n_gen = len(self.generators)
        n_time = len(self.demand_profile)
        
        for epsilon in emission_levels:
            # Decision variables
            P = cp.Variable((n_gen, n_time), nonneg=True)
            
            # Minimize cost
            cost_obj = 0
            for t in range(n_time):
                for i, gen in enumerate(self.generators):
                    cost_obj += gen['a'] * cp.square(P[i, t]) + gen['b'] * P[i, t] + gen['c']
            
            # Emission constraint
            emission_constraint = 0
            for t in range(n_time):
                for i, gen in enumerate(self.generators):
                    emission_constraint += gen['emission_rate'] * P[i, t]
            
            # Constraints
            constraints = []
            
            # Power balance
            for t in range(n_time):
                constraints.append(cp.sum(P[:, t]) == self.demand_profile[t])
            
            # Generator limits
            for i, gen in enumerate(self.generators):
                for t in range(n_time):
                    constraints.append(P[i, t] >= gen['pmin'])
                    constraints.append(P[i, t] <= gen['pmax'])
            
            # Ramping constraints
            for i, gen in enumerate(self.generators):
                for t in range(1, n_time):
                    constraints.append(P[i, t] - P[i, t-1] <= gen['ramp_up'])
                    constraints.append(P[i, t-1] - P[i, t] <= gen['ramp_down'])
            
            # Emission constraint
            constraints.append(emission_constraint <= epsilon)
            
            # Solve
            problem = cp.Problem(cp.Minimize(cost_obj), constraints)
            problem.solve(solver=cp.OSQP, verbose=False)
            
            if problem.status == cp.OPTIMAL:
                solution = P.value
                cost = self._calculate_total_cost(solution)
                emissions = self._calculate_emissions(solution)
                
                pareto_solutions.append(solution)
                pareto_costs.append(cost)
                pareto_emissions.append(emissions)
        
        if pareto_solutions:
            # Store results
            middle_idx = len(pareto_solutions) // 2
            self.solution = pareto_solutions[middle_idx]
            self.total_cost = pareto_costs[middle_idx]
            self.emissions = pareto_emissions[middle_idx]
            
            # Create weight combinations for display
            weight_combinations = [(1.0, 0.0)] * len(pareto_solutions)
            
            self.pareto_costs = pareto_costs
            self.pareto_emissions = pareto_emissions
            self.pareto_solutions = pareto_solutions
            self.weight_combinations = weight_combinations;
            
            st.success(f"Generated Pareto frontier with {len(pareto_costs)} points using epsilon-constraint method!")
            return True
        else:
            st.error("Failed to generate Pareto frontier using epsilon-constraint method!")
            return False

    def _filter_pareto_optimal(self, costs, emissions):
        """Filter to keep only Pareto optimal points"""
        n_points = len(costs)
        is_pareto = [True] * n_points
        
        for i in range(n_points):
            for j in range(n_points):
                if i != j:
                    # Point j dominates point i if j is better in both objectives
                    if (costs[j] <= costs[i] and emissions[j] <= emissions[i] and 
                        (costs[j] < costs[i] or emissions[j] < emissions[i])):
                        is_pareto[i] = False
                        break
        
        return [i for i in range(n_points) if is_pareto[i]]
    
    def _calculate_total_cost(self, solution):
        """Calculate total cost for given solution"""
        cost = 0
        n_time = solution.shape[1]
        for t in range(n_time):
            for i, gen in enumerate(self.generators):
                p = solution[i, t]
                cost += gen['a'] * p**2 + gen['b'] * p + gen['c']
        return cost
    
    def _calculate_emissions(self, solution):
        """Calculate total emissions for given solution"""
        emissions = 0
        n_time = solution.shape[1]
        for t in range(n_time):
            for i, gen in enumerate(self.generators):
                emissions += gen['emission_rate'] * solution[i, t]
        return emissions

def initialize_session_state():
    """Initialize session state variables"""
    if 'generators' not in st.session_state:
        st.session_state.generators = [
            {'name': 'Coal1', 'type': 'Coal', 'pmin': 50, 'pmax': 400, 'a': 0.008, 'b': 25, 'c': 80, 'ramp_up': 60, 'ramp_down': 60, 'emission_rate': 0.95},
            {'name': 'Gas1', 'type': 'Gas', 'pmin': 20, 'pmax': 250, 'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 100, 'ramp_down': 100, 'emission_rate': 0.45},
            {'name': 'Hydro1', 'type': 'Hydro', 'pmin': 30, 'pmax': 200, 'a': 0.002, 'b': 10, 'c': 20, 'ramp_up': 150, 'ramp_down': 150, 'emission_rate': 0.02}
        ]
    
    if 'demand_profile' not in st.session_state:
        st.session_state.demand_profile = [400, 450, 500, 480, 420, 380, 360, 400, 450, 500, 480, 420]
    
    if 'problem_type' not in st.session_state:
        st.session_state.problem_type = "ED-2"
    
    if 'solutions' not in st.session_state:
        st.session_state.solutions = {}
    
    if 'emission_limit' not in st.session_state:
        st.session_state.emission_limit = 400

def create_demand_profile(pattern, base_load, hours):
    """Create demand profile based on pattern"""
    if pattern == "Flat":
        return [base_load] * hours
    elif pattern == "Peak/Off-Peak":
        profile = []
        for h in range(hours):
            if 6 <= h <= 18:  # Peak hours (6 AM to 6 PM)
                profile.append(int(base_load * 1.3))
            else:  # Off-peak hours
                profile.append(base_load)
        return profile
    elif pattern == "Realistic Daily":
        # Realistic 24-hour load curve
        hourly_factors = [0.7, 0.6, 0.6, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.2, 1.3,
                         1.3, 1.2, 1.2, 1.3, 1.4, 1.5, 1.4, 1.3, 1.2, 1.0, 0.9, 0.8]
        return [int(base_load * hourly_factors[h % 24]) for h in range(hours)]
    else:
        return [base_load] * hours

def render_sidebar():
    """Render sidebar configuration"""
    st.sidebar.markdown("## ⚙️ Configuration")
    
    # Demand Profile Settings
    st.sidebar.markdown("### ⚡ Demand Profile")
    
    hours = st.sidebar.selectbox("Time Horizon (hours)", [6, 12, 24], index=1)
    pattern = st.sidebar.selectbox("Demand Pattern", ["Flat", "Peak/Off-Peak", "Realistic Daily"], index=1)
    base_load = st.sidebar.slider("Base Load (MW)", 200, 600, 400, 50)
    
    # Check if demand profile parameters changed
    new_demand_profile = create_demand_profile(pattern, base_load, hours)
    
    # Clear solutions if demand profile changed (different length or values)
    if (len(new_demand_profile) != len(st.session_state.demand_profile) or 
        new_demand_profile != st.session_state.demand_profile):
        st.session_state.solutions = {}
        if len(new_demand_profile) != len(st.session_state.demand_profile):
            st.info(f"Time horizon changed to {hours} hours. Previous solutions cleared.")
    
    # Update demand profile
    st.session_state.demand_profile = new_demand_profile
    
    # Emission Limit
    st.sidebar.markdown("### 🌱 Emission Constraint (ED-4 & ED-5)")
    emission_limit = st.sidebar.slider("Emission Limit (tons/h)", 100, 1000, 
                                      st.session_state.get('emission_limit', 400), 50)
    st.session_state.emission_limit = emission_limit
    
    # Generator Fleet Size - Only adjust if different from current
    st.sidebar.markdown("### 🏭 Generator Fleet")
    current_n_generators = len(st.session_state.generators)
    n_generators = st.sidebar.slider("Number of Generators", 2, 6, current_n_generators)
    
    # Only modify generators if count changed
    if n_generators != current_n_generators:
        # Clear existing solutions when generator count changes
        st.session_state.solutions = {}
        st.info("Generator count changed. Previous solutions cleared.")
        
        # Adjust generator list size
        if n_generators > current_n_generators:
            # Add new generators
            for i in range(current_n_generators, n_generators):
                st.session_state.generators.append({
                    'name': f'Gen{i+1}', 'type': 'Gas', 'pmin': 20, 'pmax': 200, 
                    'a': 0.015, 'b': 35, 'c': 50, 'ramp_up': 80, 'ramp_down': 80, 'emission_rate': 0.45
                })
        else:
            # Remove generators
            st.session_state.generators = st.session_state.generators[:n_generators]
    
    # Quick Actions
    st.sidebar.markdown("### 🎯 Quick Actions")
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("🔄 Reset", key="reset"):
            # Clear session state and reinitialize
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            initialize_session_state()
            st.rerun()
    
    with col2:
        if st.button("🚀 Solve All", key="solve_all", type="primary"):
            solve_all_problems()

def solve_all_problems():
    """Solve all ED problems and store results"""
    problem_types = ["ED-2", "ED-3", "ED-4", "ED-5"]
    
    with st.spinner("Solving all ED problems..."):
        for prob_type in problem_types:
            ed_problem = EDProblem(st.session_state.generators, 
                                 st.session_state.demand_profile, 
                                 prob_type)
            
            if ed_problem.solve():
                st.session_state.solutions[prob_type] = {
                    'solution': ed_problem.solution,
                    'total_cost': ed_problem.total_cost,
                    'emissions': ed_problem.emissions,
                    'problem': ed_problem
                }
    
    if len(st.session_state.solutions) == 4:
        st.success("✅ All problems solved successfully!")
    else:
        st.warning(f"⚠️ Only {len(st.session_state.solutions)} out of 4 problems solved successfully.")

def get_problem_name(prob_type):
    """Get descriptive name for problem type"""
    names = {
        "ED-1": "Basic Unconstrained ED",
        "ED-2": "With Generator Limits", 
        "ED-3": "Multi-Period with Ramping",
        "ED-4": "With Emission Constraints",
        "ED-5": "Multi-Objective (Cost vs Emissions)"
    }
    return names.get(prob_type, prob_type)

def get_problem_description(prob_type):
    """Get detailed description for problem type"""
    descriptions = {
        "ED-1": "ED-1: Basic Unconstrained ED\n(No generator limits)",
        "ED-2": "ED-2: With Generator Limits\n(Min/Max power constraints)", 
        "ED-2 (Ramping Adj.)": "ED-2: With Generator Limits\n(Ramping-adjusted solution)",
        "ED-3": "ED-3: Multi-Period with Ramping\n(Ramp rate constraints)",
        "ED-4": "ED-4: With Emission Constraints\n(Environmental limits)",
        "ED-5": "ED-5: Multi-Objective\n(Cost vs Emissions trade-off)"
    }
    return descriptions.get(prob_type, prob_type)

def preamble() -> None:
    """Everything week 7's main() did before drawing its tabs."""
    initialize_session_state()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    # Header
    st.markdown('<h1 class="main-header">⚡ Economic Dispatch Comparison Dashboard</h1>',
                unsafe_allow_html=True)

    # Sidebar
    render_sidebar()


def postamble() -> None:
    """Everything week 7's main() did after its tabs."""
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
    <p><strong>Economic Dispatch Comparison Dashboard</strong></p>
    <p>Comparing ED-2 (Limits) • ED-3 (Ramping) • ED-4 (Emissions) • ED-5 (Multi-objective)</p>
    </div>
    """, unsafe_allow_html=True)


def page(tab_body: Optional[Callable[[], None]] = None) -> None:
    """Render the shared dispatch page around the caller's own tab body.

    ``tab_body`` is invoked at the point where week7_ed_viu.py rendered its
    ``st.tabs`` block, so the footer below it still appears after it, as it
    does today.
    """
    preamble()
    if tab_body is not None:
        tab_body()
    postamble()
