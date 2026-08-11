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

# Page configuration
st.set_page_config(
    page_title="Economic Dispatch Comparison Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
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
""", unsafe_allow_html=True)

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
    
    # Rest of the function remains the same for the interactive analysis...
def main():
    """Main application function"""
    initialize_session_state()
    
    # Header
    st.markdown('<h1 class="main-header">⚡ Economic Dispatch Comparison Dashboard</h1>', 
                unsafe_allow_html=True)
    
    # Sidebar
    render_sidebar()
    
    # Main content
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏭 Generator Setup", 
        "📊 Comparison Results",
        "🔍 Detailed Analysis", 
        "📈 Individual Generators",
        "🎯 Pareto Frontier"
    ])
    
    with tab1:
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
    
    with tab2:
        render_comparison_results()
    
    with tab3:
        render_detailed_analysis()
    
    with tab4:
        render_individual_generator_analysis()
    
    with tab5:
        render_pareto_frontier()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
    <p><strong>Economic Dispatch Comparison Dashboard</strong></p>
    <p>Comparing ED-2 (Limits) • ED-3 (Ramping) • ED-4 (Emissions) • ED-5 (Multi-objective)</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
