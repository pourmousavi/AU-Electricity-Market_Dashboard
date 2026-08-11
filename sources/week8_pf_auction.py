import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional  # noqa: F401
import networkx as nx
import warnings
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="Double-Sided Electricity Market Dashboard",
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
    .generator-card {
        background-color: #ffe6e6;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.2rem 0;
    }
    .retailer-card {
        background-color: #e6f3ff;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.2rem 0;
    }
</style>
""", unsafe_allow_html=True)


class ElectricityMarket:
    def __init__(self, generators, retailers, network):
        self.generators = generators
        self.retailers = retailers
        self.network = network
        self.market_price = None
        self.dispatched_generation = None
        self.dispatched_demand = None
        self.cleared_quantity = None
        self.generator_revenues = None
        self.retailer_costs = None
        
    def solve_market(self):
        """Solve the double-sided market clearing problem"""
        try:
            # Create supply and demand curves
            supply_bids = []
            demand_bids = []
            
            # Process generator bids (supply)
            for gen_id, gen in enumerate(self.generators):
                for bid_idx, (quantity, price) in enumerate(
                    zip(gen['quantities'], gen['prices'])
                ):
                    supply_bids.append({
                        'quantity': quantity,
                        'price': price,
                        'gen_id': gen_id,
                        'bid_id': bid_idx,
                        'type': 'supply',
                        'cumulative_qty': 0
                    })
            
            # Process retailer bids (demand)
            for ret_id, ret in enumerate(self.retailers):
                for bid_idx, (quantity, price) in enumerate(
                    zip(ret['quantities'], ret['prices'])
                ):
                    demand_bids.append({
                        'quantity': quantity,
                        'price': price,
                        'ret_id': ret_id,
                        'bid_id': bid_idx,
                        'type': 'demand',
                        'cumulative_qty': 0
                    })
            
            # Sort supply bids by price (ascending)
            supply_bids.sort(key=lambda x: x['price'])
            # Sort demand bids by price (descending)
            demand_bids.sort(key=lambda x: x['price'], reverse=True)
            
            # Create cumulative quantities
            cumulative_supply = 0
            for bid in supply_bids:
                bid['cumulative_qty'] = cumulative_supply
                cumulative_supply += bid['quantity']
            
            cumulative_demand = 0
            for bid in demand_bids:
                bid['cumulative_qty'] = cumulative_demand
                cumulative_demand += bid['quantity']
            
            # Find market clearing point
            market_price, cleared_quantity = self._find_market_clearing(
                supply_bids, demand_bids
            )
            
            if market_price is None:
                return False
            
            # Store market clearing results first
            self.market_price = market_price
            self.cleared_quantity = cleared_quantity
            
            # Dispatch based on market clearing price and quantity
            dispatched_gen = self._dispatch_generation(
                supply_bids, cleared_quantity
            )
            dispatched_demand = self._dispatch_demand(
                demand_bids, cleared_quantity
            )
            
            # Store results
            self.dispatched_generation = dispatched_gen
            self.dispatched_demand = dispatched_demand
            self.supply_bids = supply_bids
            self.demand_bids = demand_bids
            
            # Calculate revenues and costs
            self._calculate_financial_outcomes()
            
            return True
            
        except Exception as e:
            st.error(f"Market solving error: {str(e)}")
            return False
    
    def _find_market_clearing(self, supply_bids, demand_bids):
        """Find the intersection of supply and demand curves"""
        if not supply_bids or not demand_bids:
            return None, None
        
        # Find maximum possible trade quantity
        max_supply = sum(bid['quantity'] for bid in supply_bids)
        max_demand = sum(bid['quantity'] for bid in demand_bids)
        max_quantity = min(max_supply, max_demand)
        
        if max_quantity == 0:
            return None, None
        
        # Build step function for supply and demand
        # Supply curve: price increases with quantity
        # Demand curve: price decreases with quantity
        
        # Find the crossing point by checking each quantity level
        best_quantity = 0
        best_price = None
        
        # Check at each MW increment
        for quantity in range(0, int(max_quantity) + 1, 1):
            supply_price = self._get_supply_price_at_quantity(
                supply_bids, quantity
            )
            demand_price = self._get_demand_price_at_quantity(
                demand_bids, quantity
            )
            
            if supply_price is not None and demand_price is not None:
                # Market clears where supply price <= demand price
                # The last quantity where this is true is the clearing quantity
                if supply_price <= demand_price:
                    best_quantity = quantity
                    # Use higher price
                    best_price = max(supply_price, demand_price)
                else:
                    # We've passed the intersection, stop here
                    break
        
        if best_price is not None and best_quantity > 0:
            return best_price, best_quantity
        
        return None, None
    
    def _get_supply_price_at_quantity(self, supply_bids, quantity):
        """Get supply price at given quantity"""
        if quantity == 0:
            return supply_bids[0]['price'] if supply_bids else None
        
        cumulative = 0
        for bid in supply_bids:
            if cumulative < quantity <= cumulative + bid['quantity']:
                return bid['price']
            cumulative += bid['quantity']
            
        # If quantity exceeds total supply, return highest price
        if supply_bids and quantity > cumulative:
            return supply_bids[-1]['price']
        
        return None
    
    def _get_demand_price_at_quantity(self, demand_bids, quantity):
        """Get demand price at given quantity"""
        if quantity == 0:
            return demand_bids[0]['price'] if demand_bids else None
        
        cumulative = 0
        for bid in demand_bids:
            if cumulative < quantity <= cumulative + bid['quantity']:
                return bid['price']
            cumulative += bid['quantity']
            
        # If quantity exceeds total demand, return lowest price
        if demand_bids and quantity > cumulative:
            return demand_bids[-1]['price']
        
        return None
    
    def _dispatch_generation(self, supply_bids, cleared_quantity):
        """Determine generator dispatch based on market clearing"""
        dispatch = {}
        remaining_quantity = cleared_quantity
        
        # Initialize dispatch for all generators
        for gen in self.generators:
            dispatch[gen['name']] = 0
        
        # Only dispatch generators with bids at or below market clearing price
        for bid in supply_bids:
            if remaining_quantity <= 0:
                break
            
            # Only dispatch if bid price is at or below market clearing price
            if bid['price'] <= self.market_price:
                gen_name = self.generators[bid['gen_id']]['name']
                dispatch_qty = min(bid['quantity'], remaining_quantity)
                dispatch[gen_name] += dispatch_qty
                remaining_quantity -= dispatch_qty
            else:
                # Stop dispatching when we reach bids above clearing price
                break
        
        return dispatch
    
    def _dispatch_demand(self, demand_bids, cleared_quantity):
        """Determine retailer dispatch based on market clearing"""
        dispatch = {}
        remaining_quantity = cleared_quantity
        
        # Initialize dispatch for all retailers
        for ret in self.retailers:
            dispatch[ret['name']] = 0
        
        # Only dispatch retailers with bids at or above market clearing price
        for bid in demand_bids:
            if remaining_quantity <= 0:
                break
            
            # Only dispatch if bid price is at or above market clearing price
            if bid['price'] >= self.market_price:
                ret_name = self.retailers[bid['ret_id']]['name']
                dispatch_qty = min(bid['quantity'], remaining_quantity)
                dispatch[ret_name] += dispatch_qty
                remaining_quantity -= dispatch_qty
            else:
                # Stop dispatching when we reach bids below clearing price
                break
        
        return dispatch
    
    def _calculate_financial_outcomes(self):
        """Calculate revenues for generators and costs for retailers"""
        self.generator_revenues = {}
        self.retailer_costs = {}
        
        # Generator revenues (market price * dispatched quantity)
        for gen in self.generators:
            dispatched = self.dispatched_generation.get(gen['name'], 0)
            self.generator_revenues[gen['name']] = (
                dispatched * self.market_price
            )
        
        # Retailer costs (market price * dispatched quantity)
        for ret in self.retailers:
            dispatched = self.dispatched_demand.get(ret['name'], 0)
            self.retailer_costs[ret['name']] = dispatched * self.market_price


class OptimalDCPowerFlow:
    """DC OPF solver using CVXPY"""
    
    def __init__(self, network):
        self.network = network
        self.solved = False
        self.generation_dispatch = None
        self.demand_dispatch = None
        self.line_flows = None
        self.total_cost = None
        self.shadow_prices = None
        self.congested_lines = []
        
    def display_mathematical_formulation(self):
        """Display the complete DC OPF mathematical formulation with
        actual system values"""
        
        # Get current system data
        generators = (
            st.session_state.generators
            if hasattr(st.session_state, 'generators')
            else []
        )
        retailers = (
            st.session_state.retailers
            if hasattr(st.session_state, 'retailers')
            else []
        )
        buses = self.network['buses']
        lines = self.network['lines']
        
        # Create expandable section for the mathematical formulation
        with st.expander(
            "🔍 **Click to view complete mathematical formulation** "
            "**with actual values**",
            expanded=False,
        ):
            
            # Display system dimensions
            n_gen = len(generators)
            n_ret = len(retailers) 
            n_bus = len(buses)
            n_lines = len(lines)
            
            st.markdown("### **System Dimensions:**")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"- **Generators**: {n_gen}")
                st.markdown(f"- **Retailers**: {n_ret}")
            with col2:
                st.markdown(f"- **Buses**: {n_bus}")
                st.markdown(f"- **Transmission Lines**: {n_lines}")
            
            st.markdown("### **Decision Variables:**")
            
            # Count total bid blocks
            total_gen_bids = sum(len(gen['quantities']) for gen in generators)
            total_ret_bids = sum(len(ret['quantities']) for ret in retailers)
            
            st.latex(r"""
            \mathbf{Variables:}
            """)
            
            st.markdown(f"**Generator Bid Variables:** $P_{{gen,k}}$ for $k = 1, \\ldots, {total_gen_bids}$ (MW)")
            st.markdown(f"**Retailer Bid Variables:** $P_{{ret,j}}$ for $j = 1, \\ldots, {total_ret_bids}$ (MW)")
            st.markdown(f"**Voltage Angles:** $\\theta_n$ for $n = 1, \\ldots, {n_bus}$ (radians)")
            
            st.markdown("### **Objective Function: Social Welfare Maximization**")
            
            st.latex(r"""
            \max \quad \sum_{j=1}^{""" + str(total_ret_bids) + r"""} u_j P_{ret,j} - \sum_{k=1}^{""" + str(total_gen_bids) + r"""} c_k P_{gen,k}
            """)
            
            # Display actual bid values
            if generators and retailers:
                st.markdown("### **Actual Parameter Values:**")
                
                # Generator costs
                with st.expander("Generator Bid Costs ($c_k$)", expanded=False):
                    for gen_idx, gen in enumerate(generators):
                        st.markdown(f"**{gen['name']} (Bus {gen['bus']+1}):**")
                        for bid_idx, price in enumerate(gen['prices']):
                            st.markdown(f"  - Bid {bid_idx+1}: ${price}/MWh")
                
                # Retailer utilities  
                with st.expander("Retailer Bid Utilities ($u_j$)", expanded=False):
                    for ret_idx, ret in enumerate(retailers):
                        st.markdown(f"**{ret['name']} (Bus {ret['bus']+1}):**")
                        for bid_idx, price in enumerate(ret['prices']):
                            st.markdown(f"  - Bid {bid_idx+1}: ${price}/MWh")
                
                # Generator capacities
                with st.expander("Generator Capacities", expanded=False):
                    for gen_idx, gen in enumerate(generators):
                        max_cap = gen['max_capacity']
                        st.markdown(f"**{gen['name']}:** {max_cap} MW maximum")
                        for bid_idx, qty in enumerate(gen['quantities']):
                            st.markdown(f"  - Bid {bid_idx+1}: {qty} MW")
                
                # Retailer demands
                with st.expander("Retailer Demand Limits", expanded=False):
                    for ret_idx, ret in enumerate(retailers):
                        st.markdown(f"**{ret['name']}:**")
                        for bid_idx, qty in enumerate(ret['quantities']):
                            st.markdown(f"  - Bid {bid_idx+1}: {qty} MW")
            
            # Network parameters
            st.markdown("### **Network Parameters:**")
            with st.expander("Transmission Line Data", expanded=False):
                st.markdown("Base Power: $S_{base} = 100$ MVA")
                st.markdown("Base Voltage: $V_{base} = 138$ kV")
                st.markdown("")
                st.markdown("**Line Parameters:**")
                for line in lines:
                    reactance = line['reactance']
                    susceptance = 1/reactance
                    rating = line['rating']
                    st.markdown(f"Line {line['from_bus']+1}→{line['to_bus']+1}: X={reactance:.4f} p.u., B={susceptance:.2f} p.u.⁻¹, Rating={rating} MW")
            
            st.markdown("### **Constraints:**")
            
            st.markdown("#### **1. Generator Bid Block Limits**")
            st.latex(r"""
            0 \leq P_{gen,k} \leq Q_{gen,k}^{\max} \quad \forall k \in \{1, \ldots, """ + str(total_gen_bids) + r"""\}
            """)
            
            st.markdown("#### **2. Retailer Bid Block Limits**")
            st.latex(r"""
            0 \leq P_{ret,j} \leq Q_{ret,j}^{\max} \quad \forall j \in \{1, \ldots, """ + str(total_ret_bids) + r"""\}
            """)
            
            st.markdown("#### **3. Generator Capacity Constraints**")
            st.latex(r"""
            \sum_{k \in \mathcal{K}_i} P_{gen,k} \leq P_{G,i}^{\max} \quad \forall i \in \{1, \ldots, """ + str(n_gen) + r"""\}
            """)
            st.markdown("Where $\\mathcal{K}_i$ is the set of bid blocks for generator $i$")
            
            st.markdown("#### **4. Slack Bus Constraint**")
            st.latex(r"""
            \theta_1 = 0 \text{ radians}
            """)
            
            st.markdown("#### **5. Nodal Power Balance (DC Power Flow)**")
            st.markdown("Individual nodal balance equations with actual parameter values:")
            
            # Create the actual nodal balance equations with real parameters
            for bus_idx in range(n_bus):
                if bus_idx == 0:  # Skip slack bus
                    continue
                    
                bus_num = bus_idx + 1
                st.markdown(f"**Bus {bus_num} Balance:**")
                
                # Find generators at this bus
                gens_at_bus = [i for i, gen in enumerate(generators) if gen['bus'] == bus_idx]
                rets_at_bus = [i for i, ret in enumerate(retailers) if ret['bus'] == bus_idx]
                
                # Find connected lines
                connected_lines = []
                for line in lines:
                    if line['from_bus'] == bus_idx:
                        connected_lines.append((line['to_bus'], line['reactance'], 'from'))
                    elif line['to_bus'] == bus_idx:
                        connected_lines.append((line['from_bus'], line['reactance'], 'to'))
                
                # Build the equation string
                equation_parts = []
                
                # Generation terms
                if gens_at_bus:
                    gen_terms = []
                    for gen_idx in gens_at_bus:
                        gen_name = generators[gen_idx]['name']
                        n_bids = len(generators[gen_idx]['quantities'])
                        for bid in range(n_bids):
                            gen_terms.append(f"P_{{{gen_name},bid{bid+1}}}")
                    if gen_terms:
                        equation_parts.append(" + ".join(gen_terms))
                else:
                    equation_parts.append("0")
                
                equation_parts.append(" - ")
                
                # Demand terms  
                if rets_at_bus:
                    ret_terms = []
                    for ret_idx in rets_at_bus:
                        ret_name = retailers[ret_idx]['name']
                        n_bids = len(retailers[ret_idx]['quantities'])
                        for bid in range(n_bids):
                            ret_terms.append(f"P_{{{ret_name},bid{bid+1}}}")
                    if ret_terms:
                        equation_parts.append(" - ".join(ret_terms))
                else:
                    equation_parts.append("0")
                
                equation_parts.append(" = ")
                
                # Power flow terms
                if connected_lines:
                    flow_terms = []
                    for other_bus, reactance, direction in connected_lines:
                        susceptance = 1/reactance
                        other_bus_num = other_bus + 1
                        flow_terms.append(f"{susceptance:.2f} \\times (\\theta_{{{bus_num}}} - \\theta_{{{other_bus_num}}})")
                    equation_parts.append("100 \\times (" + " + ".join(flow_terms) + ")")
                else:
                    equation_parts.append("0")
                
                # Display the equation
                equation_latex = "".join(equation_parts)
                st.latex(equation_latex)
                
                # Show parameter details
                with st.expander(f"Bus {bus_num} Details", expanded=False):
                    if gens_at_bus:
                        st.markdown("**Generators at this bus:**")
                        for gen_idx in gens_at_bus:
                            gen = generators[gen_idx]
                            st.markdown(f"- {gen['name']}: {len(gen['quantities'])} bid blocks")
                    if rets_at_bus:
                        st.markdown("**Retailers at this bus:**")
                        for ret_idx in rets_at_bus:
                            ret = retailers[ret_idx]
                            st.markdown(f"- {ret['name']}: {len(ret['quantities'])} bid blocks")
                    if connected_lines:
                        st.markdown("**Connected lines:**")
                        for other_bus, reactance, direction in connected_lines:
                            susceptance = 1/reactance
                            st.markdown(f"- To Bus {other_bus+1}: X={reactance:.4f} p.u., B={susceptance:.2f} p.u.⁻¹")
            
            st.markdown("#### **6. Voltage Angle Limits**")
            st.latex(r"""
            -\pi \leq \theta_n \leq \pi \quad \forall n \in \{2, \ldots, """ + str(n_bus) + r"""\}
            """)
            
            st.markdown("#### **7. Transmission Line Thermal Limits**")
            for line_idx, line in enumerate(lines):
                from_bus = line['from_bus'] + 1
                to_bus = line['to_bus'] + 1
                rating = line['rating']
                susceptance = 1/line['reactance']
                
                st.latex(f"""
                -{rating} \\leq {susceptance:.2f} \\times (\\theta_{{{from_bus}}} - \\theta_{{{to_bus}}}) \\times 100 \\leq {rating}
                """)
            
            st.markdown("### **Solution Method:**")
            st.markdown("- **Solver**: CVXPY with CLARABEL/ECOS/OSQP")
            st.markdown("- **Problem Type**: Linear Program (LP)")
            st.markdown("- **Dual Variables**: Extract LMPs from nodal balance constraints")
            st.markdown("- **Expected Result**: Optimal solution with positive LMPs")
        
    def solve_optimal_dispatch(self):
        """Solve double-sided DC OPF with voltage and transmission constraints"""
        
        try:
            import cvxpy as cp
            
            # System parameters with explicit units
            S_base = 100.0  # MVA base power
            V_base = 138.0  # kV base voltage (reference, not used in DC OPF)
            
            # Unit consistency notes:
            # - All reactances are in p.u. (per-unit)
            # - All susceptances B = 1/X are in p.u.^-1
            # - All angles θ are in radians
            # - All power flows P = B*(θ₁-θ₂)*S_base are in MW
            # - All thermal limits are in MW
            # - DC approximation: |V| = 1.0 p.u. everywhere
            
            buses = self.network['buses']
            lines = self.network['lines']
            n_bus = len(buses)
            
            # Generator and retailer data from session state
            generators = st.session_state.generators
            retailers = st.session_state.retailers
            n_gen = len(generators)
            n_ret = len(retailers)
            
            # Create bid-level decision variables for proper market representation
            
            # Generator bid blocks
            gen_bid_blocks = []
            gen_bid_costs = []
            gen_bid_quantities = []
            gen_to_bids = {}  # Map generator index to its bid indices
            
            for gen_idx, gen in enumerate(generators):
                gen_to_bids[gen_idx] = []
                for bid_idx, (qty, price) in enumerate(zip(gen['quantities'], gen['prices'])):
                    bid_block_idx = len(gen_bid_blocks)
                    gen_bid_blocks.append({
                        'gen_idx': gen_idx,
                        'bid_idx': bid_idx,
                        'quantity': qty,
                        'price': price,
                        'gen_name': gen['name']
                    })
                    gen_bid_costs.append(price)
                    gen_bid_quantities.append(qty)
                    gen_to_bids[gen_idx].append(bid_block_idx)
            
            # Retailer bid blocks
            ret_bid_blocks = []
            ret_bid_utilities = []
            ret_bid_quantities = []
            ret_to_bids = {}  # Map retailer index to its bid indices
            
            for ret_idx, ret in enumerate(retailers):
                ret_to_bids[ret_idx] = []
                for bid_idx, (qty, price) in enumerate(zip(ret['quantities'], ret['prices'])):
                    bid_block_idx = len(ret_bid_blocks)
                    ret_bid_blocks.append({
                        'ret_idx': ret_idx,
                        'bid_idx': bid_idx,
                        'quantity': qty,
                        'price': price,
                        'ret_name': ret['name']
                    })
                    ret_bid_utilities.append(price)
                    ret_bid_quantities.append(qty)
                    ret_to_bids[ret_idx].append(bid_block_idx)
            
            # Decision variables for each bid block
            P_gen_bids = cp.Variable(len(gen_bid_blocks), name="P_gen_bids")  # MW per gen bid
            P_load_bids = cp.Variable(len(ret_bid_blocks), name="P_load_bids")  # MW per ret bid
            theta = cp.Variable(n_bus, name="theta")  # Voltage angles (rad)
            
            st.info("📋 **Bid Structure:**")
            st.info(f"   • Generator bid blocks: {len(gen_bid_blocks)}")
            st.info(f"   • Retailer bid blocks: {len(ret_bid_blocks)}")
            
            # Show detailed bid structure for debugging
            with st.expander("🔍 View Detailed Bid Structure", expanded=False):
                st.markdown("**Generator Bids:**")
                for i, bid in enumerate(gen_bid_blocks):
                    st.write(f"Bid {i}: {bid['gen_name']} - {bid['quantity']} MW @ ${bid['price']}/MWh")
                
                st.markdown("**Retailer Bids:**")
                for i, bid in enumerate(ret_bid_blocks):
                    st.write(f"Bid {i}: {bid['ret_name']} - {bid['quantity']} MW @ ${bid['price']}/MWh")
            
            # Objective: Maximize social welfare using actual bid prices
            generation_cost = gen_bid_costs @ P_gen_bids
            consumer_utility = ret_bid_utilities @ P_load_bids
            social_welfare = consumer_utility - generation_cost
            
            objective = cp.Maximize(social_welfare)
            
            # Constraints
            constraints = []
            
            # 1. Bid block quantity limits (each bid block cannot exceed its offered quantity)
            for i, bid_block in enumerate(gen_bid_blocks):
                constraints.append(P_gen_bids[i] >= 0)
                constraints.append(P_gen_bids[i] <= bid_block['quantity'])
            
            for i, bid_block in enumerate(ret_bid_blocks):
                constraints.append(P_load_bids[i] >= 0)
                constraints.append(P_load_bids[i] <= bid_block['quantity'])
            
            # 2. Generator capacity limits (sum of all bids per generator)
            for gen_idx, gen in enumerate(generators):
                gen_bid_indices = gen_to_bids[gen_idx]
                if gen_bid_indices:  # Only if generator has bids
                    total_gen_output = cp.sum([P_gen_bids[i] for i in gen_bid_indices])
                    constraints.append(total_gen_output >= 0)
                    constraints.append(total_gen_output <= gen['max_capacity'])
            
            # 3. Retailer capacity limits (sum of all bids per retailer)
            for ret_idx, ret in enumerate(retailers):
                ret_bid_indices = ret_to_bids[ret_idx]
                if ret_bid_indices:  # Only if retailer has bids
                    total_ret_demand = cp.sum([P_load_bids[i] for i in ret_bid_indices])
                    max_demand = sum(ret['quantities']) if ret['quantities'] else 100
                    constraints.append(total_ret_demand >= 0)
                    constraints.append(total_ret_demand <= max_demand)
            
            # 3. Voltage angle limits (physical constraint)
            for i in range(n_bus):
                constraints.append(theta[i] >= -np.pi)  # Minimum angle limit
                constraints.append(theta[i] <= np.pi)   # Maximum angle limit
            
            # 4. System-wide power balance constraint (redundant with nodal balances)
            # Removed to avoid dual degeneracy that distorts LMPs. Nodal balances enforce
            # system balance when summed across all buses.
            
            # 6. Nodal power balance constraints (DC power flow equations)
            # These work together with system balance to ensure proper dispatch
            nodal_balance_constraints = []
            for bus_idx in range(n_bus):
                # Enforce angle reference at the slack bus
                if bus_idx == 0:
                    constraints.append(theta[bus_idx] == 0)
                
                # Net injection at this bus (MW)
                net_injection = cp.Constant(0)
                
                # Add generation at this bus (sum all bid blocks for generators at this bus)
                for gen_idx, gen in enumerate(generators):
                    if gen['bus'] == bus_idx:
                        gen_bid_indices = gen_to_bids[gen_idx]
                        for bid_idx in gen_bid_indices:
                            net_injection += P_gen_bids[bid_idx]
                
                # Subtract load at this bus (sum all bid blocks for retailers at this bus)
                for ret_idx, ret in enumerate(retailers):
                    if ret['bus'] == bus_idx:
                        ret_bid_indices = ret_to_bids[ret_idx]
                        for bid_idx in ret_bid_indices:
                            net_injection -= P_load_bids[bid_idx]
                
                # Line flows from this bus (MW)
                line_flows_sum = cp.Constant(0)
                for line in lines:
                    if line['from_bus'] == bus_idx:
                        # Power flows out (positive)
                        susceptance = 1 / line['reactance']  # [p.u.^-1]
                        # DC power flow: P = B*(θ₁-θ₂)*S_base
                        # Units: [p.u.^-1] * [rad] * [MVA] = [MW]
                        line_flow_pu = susceptance * (theta[bus_idx] - theta[line['to_bus']])
                        line_flow_mw = line_flow_pu * S_base  # Convert to MW
                        line_flows_sum += line_flow_mw
                    elif line['to_bus'] == bus_idx:
                        # Power flows in (negative)
                        susceptance = 1 / line['reactance']  # [p.u.^-1]
                        # DC power flow: P = B*(θ₁-θ₂)*S_base
                        # Units: [p.u.^-1] * [rad] * [MVA] = [MW]
                        line_flow_pu = susceptance * (theta[line['from_bus']] - theta[bus_idx])
                        line_flow_mw = line_flow_pu * S_base  # Convert to MW
                        line_flows_sum -= line_flow_mw
                
                # Nodal balance: Net injection = Net outflow
                nodal_constraint = (net_injection == line_flows_sum)
                constraints.append(nodal_constraint)
                nodal_balance_constraints.append(nodal_constraint)
            
            # 7. Transmission line thermal limits
            line_thermal_constraints = []
            for line in lines:
                from_bus = line['from_bus']
                to_bus = line['to_bus']
                susceptance = 1 / line['reactance']  # [p.u.^-1]
                thermal_limit = line['rating']  # [MW]
                
                # DC power flow equation: P = B*(θ₁-θ₂)*S_base
                # Units: [p.u.^-1] * [rad] * [MVA] = [MW]
                line_flow = susceptance * (theta[from_bus] - theta[to_bus]) * S_base
                
                # Thermal limit constraints (both directions)
                # |P_line| ≤ P_thermal [MW]
                pos_constraint = (line_flow <= thermal_limit)
                neg_constraint = (line_flow >= -thermal_limit)
                constraints.append(pos_constraint)
                constraints.append(neg_constraint)
                line_thermal_constraints.extend([pos_constraint, neg_constraint])
            
            # 7. Voltage angle limits for stability
            for i in range(1, n_bus):  # Skip slack bus
                constraints.append(theta[i] >= -np.pi/6)  # -30 degrees
                constraints.append(theta[i] <= np.pi/6)   # +30 degrees
            
            # Solve the optimization problem
            problem = cp.Problem(objective, constraints)
            
            # Use appropriate solver for this problem type
            try:
                problem.solve(solver=cp.CLARABEL, verbose=False)
            except:
                try:
                    problem.solve(solver=cp.ECOS, verbose=False)
                except:
                    try:
                        problem.solve(solver=cp.OSQP, verbose=False)
                    except:
                        problem.solve(verbose=False)
            
            if problem.status not in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
                st.error(f"❌ DC OPF failed: {problem.status}")
                st.error("💡 Possible issues:")
                st.error("   • Voltage constraints too restrictive")
                st.error("   • Insufficient generation capacity")
                st.error("   • Transmission bottlenecks")
                st.error("   • Infeasible power balance")
                return False
            
            # Store results
            self.solved = True
            self.total_cost = generation_cost.value if generation_cost.value is not None else 0
            
            # Extract generation dispatch (aggregate bid blocks by generator)
            self.generation_dispatch = {}
            for gen_idx, gen in enumerate(generators):
                gen_bid_indices = gen_to_bids[gen_idx]
                total_dispatch = 0
                if P_gen_bids.value is not None:
                    for bid_idx in gen_bid_indices:
                        total_dispatch += max(0, P_gen_bids.value[bid_idx])
                self.generation_dispatch[gen['name']] = total_dispatch
            
            # Extract demand dispatch (aggregate bid blocks by retailer)
            self.demand_dispatch = {}
            for ret_idx, ret in enumerate(retailers):
                ret_bid_indices = ret_to_bids[ret_idx]
                total_dispatch = 0
                if P_load_bids.value is not None:
                    for bid_idx in ret_bid_indices:
                        total_dispatch += max(0, P_load_bids.value[bid_idx])
                self.demand_dispatch[ret['name']] = total_dispatch
            
            # Extract voltage results
            self.voltage_magnitudes = {}
            self.voltage_angles = {}
            
            # In DC OPF, voltage magnitudes are assumed 1.0 p.u. at all buses
            for i, bus in enumerate(buses):
                self.voltage_magnitudes[f"Bus {i+1}"] = 1.0
            
            if theta.value is not None:
                for i, bus in enumerate(buses):
                    self.voltage_angles[f"Bus {i+1}"] = theta.value[i]
            
            # Calculate line flows and congestion
            self.line_flows = []
            self.congested_lines = []
            self.binding_constraints = []
            
            if theta.value is not None:
                for line_idx, line in enumerate(lines):
                    from_bus = line['from_bus']
                    to_bus = line['to_bus']
                    susceptance = 1 / line['reactance']
                    thermal_limit = line['rating']
                    
                    # Calculate actual line flow
                    line_flow = susceptance * (theta.value[from_bus] - theta.value[to_bus]) * S_base
                    loading_percent = abs(line_flow) / thermal_limit * 100 if thermal_limit > 0 else 0
                    
                    self.line_flows.append({
                        'from_bus': from_bus + 1,  # Convert to 1-based
                        'to_bus': to_bus + 1,      # Convert to 1-based
                        'flow_mw': line_flow,
                        'limit_mw': thermal_limit,
                        'loading_percent': loading_percent
                    })
                    
                    # Check for thermal constraint binding (within 1% of limit)
                    if loading_percent > 99.0:
                        self.congested_lines.append({
                            'line': f"Line {from_bus+1}-{to_bus+1}",
                            'flow': line_flow,
                            'limit': thermal_limit,
                            'loading': loading_percent
                        })
                        self.binding_constraints.append(f"Thermal limit: Line {from_bus+1}-{to_bus+1}")
                
                # Note: In DC OPF, voltage constraints are not included
                # as voltage magnitudes are assumed 1.0 p.u.

            
            # Extract Locational Marginal Prices (LMPs) from dual variables
            self.shadow_prices = {}
            self.raw_duals = {}
            # We'll set this to the average LMPs for reference
            self.system_lambda = 0
            try:
                # With nodal balances enforced at all buses (including slack),
                # take the duals of those equalities. Since this is a MAX
                # problem, CVXPY returns duals with the opposite sign of
                # economic shadow prices. Hence, negate the dual values to get
                # LMPs in $/MWh.
                for bus_idx in range(n_bus):
                    dual_val = (
                        nodal_balance_constraints[bus_idx].dual_value
                        if bus_idx < len(nodal_balance_constraints)
                        else None
                    )
                    if dual_val is not None:
                        self.raw_duals[f"Bus {bus_idx + 1}"] = float(dual_val)
                        self.shadow_prices[
                            f"Bus {bus_idx + 1}"
                        ] = -float(dual_val)
                    else:
                        self.raw_duals[f"Bus {bus_idx + 1}"] = 0.0
                        self.shadow_prices[f"Bus {bus_idx + 1}"] = 0.0

                # Define a reference: use Average LMPs as the system reference
                if self.shadow_prices:
                    lmp_values = list(self.shadow_prices.values())
                    self.system_lambda = float(np.mean(lmp_values))
                else:
                    self.system_lambda = 0.0

                # Keep page quiet: no debug messaging here
                # Diagnostics are shown in the DC OPF Results tab
            except Exception as e:
                # Fallback: set all LMPs to zero on error
                st.error(f"❌ Could not extract LMPs: {str(e)}")
                for bus_idx in range(n_bus):
                    self.shadow_prices[f"Bus {bus_idx + 1}"] = 0.0
                self.system_lambda = 0.0
            
            # Verify voltage angle constraints only (DC OPF)
            # Check voltage constraint violations
            angle_violations = []
            
            # In DC OPF, voltage magnitudes are 1.0 p.u. (no violations)
            # Only check angle violations
            if hasattr(self, 'voltage_angles'):
                for bus_name, angle in self.voltage_angles.items():
                    if angle < -np.pi or angle > np.pi:
                        angle_violations.append(f"{bus_name}: {angle:.3f} rad")
            
            # Minimal success summary (keep page quiet)
            st.success("✅ DC OPF solved")
            st.caption(
                "Run 'Only Market' first for market dispatch, then 'DC OPF' "
                "for the optimal solution."
            )
            
            return True
            
        except Exception as e:
            st.error(f"DC OPF error: {str(e)}")
            import traceback
            st.error(f"Details: {traceback.format_exc()}")
            return False
    
    def _build_dc_susceptance_matrix(self):
        """Build susceptance matrix for DC power flow"""
        buses = self.network['buses']
        lines = self.network['lines']
        n_bus = len(buses)
        
        B = np.zeros((n_bus, n_bus))
        
        for line in lines:
            from_bus = line['from_bus']
            to_bus = line['to_bus']
            susceptance = 1 / line['reactance']  # B = 1/X
            
            # Fill susceptance matrix
            B[from_bus, from_bus] += susceptance
            B[to_bus, to_bus] += susceptance
            B[from_bus, to_bus] -= susceptance
            B[to_bus, from_bus] -= susceptance
        
        return B


def solve_optimal_dc_power_flow():
    """Solve DC OPF"""
    try:
        optimal_solver = OptimalDCPowerFlow(st.session_state.network)
        
        if optimal_solver.solve_optimal_dispatch():
            st.session_state.optimal_dc_results = {
                'solver': optimal_solver,
                'generation_dispatch': optimal_solver.generation_dispatch,
                'demand_dispatch': optimal_solver.demand_dispatch,
                'line_flows': optimal_solver.line_flows,
                'total_cost': optimal_solver.total_cost,
                'shadow_prices': optimal_solver.shadow_prices,
                'raw_duals': getattr(optimal_solver, 'raw_duals', {}),
                'congested_lines': optimal_solver.congested_lines,
                'system_lambda': getattr(optimal_solver, 'system_lambda', 0),
                'voltage_magnitudes': getattr(
                    optimal_solver, 'voltage_magnitudes', {}
                ),
                'voltage_angles': getattr(
                    optimal_solver, 'voltage_angles', {}
                ),
                'average_lmp': (
                    float(
                        np.mean(
                            list(optimal_solver.shadow_prices.values())
                        )
                    )
                    if optimal_solver.shadow_prices
                    else 0.0
                )
            }
            st.success("✅ DC OPF solved successfully!")
            st.info(
                "ℹ️ You can now run 'DC OPF-Based AC PF' to analyze AC "
                "power flow with this dispatch."
            )
            
        else:
            st.error("❌ DC OPF solving failed!")
            
    except Exception as e:
        st.error(f"DC OPF error: {str(e)}")


def calculate_market_dc_power_flow(market_results, network):
    """Calculate DC power flow using Market dispatch results"""
    try:
        # Build susceptance matrix
        buses = network['buses']
        lines = network['lines']
        n_bus = len(buses)
        
        B = np.zeros((n_bus, n_bus))
        
        for line in lines:
            from_bus = line['from_bus']
            to_bus = line['to_bus']
            susceptance = 1 / line['reactance']  # B = 1/X
            
            # Fill susceptance matrix
            B[from_bus, from_bus] += susceptance
            B[to_bus, to_bus] += susceptance
            B[from_bus, to_bus] -= susceptance
            B[to_bus, from_bus] -= susceptance
        
        # Calculate net injections at each bus from Market dispatch
        net_injections = np.zeros(n_bus)
        
        # Add generation from Market dispatch
        for gen_dispatch in market_results['generation_dispatch']:
            bus_id = gen_dispatch['bus']
            net_injections[bus_id] += gen_dispatch['quantity']
        
        # Subtract demand from Market dispatch
        for demand_dispatch in market_results['demand_dispatch']:
            bus_id = demand_dispatch['bus']
            net_injections[bus_id] -= demand_dispatch['quantity']
        
        # Solve DC power flow: B * θ = P (with slack bus reference)
        # Remove slack bus (bus 0) from equation system
        B_reduced = B[1:, 1:]
        P_reduced = net_injections[1:] / 100.0  # Convert to per unit (100 MVA base)
        
        # Solve for voltage angles (excluding slack bus)
        theta_reduced = np.linalg.solve(B_reduced, P_reduced)
        
        # Add slack bus angle (reference = 0)
        theta = np.concatenate([[0.0], theta_reduced])
        
        # Calculate line flows
        line_flows = {}
        for line in lines:
            from_bus = line['from_bus']
            to_bus = line['to_bus']
            susceptance = 1 / line['reactance']
            
            # Power flow: P = B * (θ_from - θ_to) * S_base
            flow_pu = susceptance * (theta[from_bus] - theta[to_bus])
            flow_mw = flow_pu * 100.0  # Convert to MW (100 MVA base)
            
            line_name = f"{buses[from_bus]['name']}-{buses[to_bus]['name']}"
            line_flows[line_name] = flow_mw
        
        return {
            'voltage_angles': {buses[i]['name']: theta[i] for i in range(n_bus)},
            'line_flows': line_flows,
            'net_injections': {buses[i]['name']: net_injections[i] for i in range(n_bus)},
            'solved': True
        }
        
    except Exception as e:
        return {
            'voltage_angles': {},
            'line_flows': {},
            'net_injections': {},
            'solved': False,
            'error': str(e)
        }


def initialize_session_state():
    """Initialize session state variables"""
    if 'generators' not in st.session_state:
        st.session_state.generators = [
            {
                'name': 'Gen1',
                'bus': 0,
                'quantities': [100, 150],
                'prices': [25, 35],
                'min_capacity': 50,
                'max_capacity': 250
            },
            {
                'name': 'Gen2', 
                'bus': 1,
                'quantities': [120, 100],
                'prices': [30, 45],
                'min_capacity': 40,
                'max_capacity': 220
            },
            {
                'name': 'Gen3',
                'bus': 2,
                'quantities': [80, 120],
                'prices': [20, 30],
                'min_capacity': 30,
                'max_capacity': 200
            }
        ]
    
    if 'retailers' not in st.session_state:
        st.session_state.retailers = [
            {
                'name': 'Retailer1',
                'bus': 3,
                'quantities': [150, 100],
                'prices': [60, 40]
            },
            {
                'name': 'Retailer2',
                'bus': 4,
                'quantities': [120, 80],
                'prices': [55, 35]
            },
            {
                'name': 'Retailer3',
                'bus': 2,
                'quantities': [100, 120],
                'prices': [50, 30]
            }
        ]
    
    if 'network' not in st.session_state:
        st.session_state.network = {
            'buses': [
                {'name': 'Bus1', 'type': 'Slack', 'v_magnitude': 1.05, 'generators': ['Gen1'], 'retailers': []},
                {'name': 'Bus2', 'type': 'PV', 'v_magnitude': 1.02, 'generators': ['Gen2'], 'retailers': []},
                {'name': 'Bus3', 'type': 'PQ', 'v_magnitude': 1.00, 'generators': ['Gen3'], 'retailers': ['Retailer3']},
                {'name': 'Bus4', 'type': 'PQ', 'v_magnitude': 1.00, 'generators': [], 'retailers': ['Retailer1']},
                {'name': 'Bus5', 'type': 'PQ', 'v_magnitude': 1.00, 'generators': [], 'retailers': ['Retailer2']}
            ],
            'lines': [
                {'from_bus': 0, 'to_bus': 1, 'resistance': 0.02, 'reactance': 0.08, 'susceptance': 0.10, 'rating': 300},
                {'from_bus': 0, 'to_bus': 3, 'resistance': 0.03, 'reactance': 0.12, 'susceptance': 0.08, 'rating': 250},
                {'from_bus': 1, 'to_bus': 2, 'resistance': 0.025, 'reactance': 0.10, 'susceptance': 0.09, 'rating': 200},
                {'from_bus': 1, 'to_bus': 4, 'resistance': 0.04, 'reactance': 0.15, 'susceptance': 0.06, 'rating': 180},
                {'from_bus': 2, 'to_bus': 3, 'resistance': 0.035, 'reactance': 0.14, 'susceptance': 0.07, 'rating': 220},
                {'from_bus': 2, 'to_bus': 4, 'resistance': 0.03, 'reactance': 0.11, 'susceptance': 0.08, 'rating': 200},
                {'from_bus': 3, 'to_bus': 4, 'resistance': 0.045, 'reactance': 0.18, 'susceptance': 0.05, 'rating': 150}
            ]
        }
    
    if 'market_results' not in st.session_state:
        st.session_state.market_results = None
    
    if 'powerflow_results' not in st.session_state:
        st.session_state.powerflow_results = None
    
    if 'optimal_dc_results' not in st.session_state:
        st.session_state.optimal_dc_results = None
    
    if 'dc_opf_powerflow_results' not in st.session_state:
        st.session_state.dc_opf_powerflow_results = None

def render_sidebar():
    """Render sidebar configuration"""
    st.sidebar.markdown("## ⚙️ Market Configuration")
    
    # Market solve button
    if st.sidebar.button("🏪 Only Market", type="primary"):
        solve_market()
    
    # DC OPF button
    if st.sidebar.button("⚡ DC OPF", type="secondary"):
        solve_optimal_dc_power_flow()
    
    if st.sidebar.button("🔄 Clear Results"):
        st.session_state.market_results = None
        st.session_state.powerflow_results = None
        st.session_state.optimal_dc_results = None
        st.session_state.dc_opf_powerflow_results = None
        st.rerun()
    
    # Network configuration
    st.sidebar.markdown("### 🔌 Network Settings")
    
    if st.sidebar.button("📊 Default Network"):
        initialize_session_state()
        st.rerun()

def solve_market():
    """Solve the electricity market"""
    try:
        market = ElectricityMarket(
            st.session_state.generators,
            st.session_state.retailers, 
            st.session_state.network
        )
        
        if market.solve_market():
            st.session_state.market_results = {
                'market': market,
                'price': market.market_price,
                'quantity': market.cleared_quantity,
                'generation_dispatch': market.dispatched_generation,
                'demand_dispatch': market.dispatched_demand,
                'generator_revenues': market.generator_revenues,
                'retailer_costs': market.retailer_costs
            }
            st.success("✅ Market solved successfully!")
        else:
            st.error("❌ Market solving failed!")
            
    except Exception as e:
        st.error(f"Market solving error: {str(e)}")

def render_market_setup():
    """Render market setup interface"""
    st.markdown("## 🏪 Market Setup")
    
    # Show info about dynamic updates
    st.info("💡 **Dynamic Configuration**: Generators and retailers are automatically created based on bus assignments in the Network Topology. Modify bus data to add/remove participants.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🔴 Generator Bids (Supply)")
        
        for i, gen in enumerate(st.session_state.generators):
            with st.expander(f"Generator: {gen['name']} (Bus {gen['bus'] + 1})", expanded=True):
                st.markdown('<div class="generator-card">', unsafe_allow_html=True)
                
                # Generator parameters
                col1_gen, col2_gen = st.columns(2)
                with col1_gen:
                    gen['min_capacity'] = st.number_input(
                        f"Min Capacity (MW)", 
                        min_value=0, max_value=500, 
                        value=gen['min_capacity'],
                        key=f"gen_min_{i}"
                    )
                with col2_gen:
                    gen['max_capacity'] = st.number_input(
                        f"Max Capacity (MW)", 
                        min_value=gen['min_capacity'], max_value=1000,
                        value=gen['max_capacity'],
                        key=f"gen_max_{i}"
                    )
                
                # Bid 1
                st.markdown("**Bid 1 (Lower Cost):**")
                col1_bid1, col2_bid1 = st.columns(2)
                with col1_bid1:
                    gen['quantities'][0] = st.number_input(
                        "Quantity 1 (MW)", 
                        min_value=0, max_value=gen['max_capacity'],
                        value=gen['quantities'][0],
                        key=f"gen_q1_{i}"
                    )
                with col2_bid1:
                    gen['prices'][0] = st.number_input(
                        "Price 1 ($/MWh)", 
                        min_value=0.0, max_value=200.0,
                        value=float(gen['prices'][0]),
                        key=f"gen_p1_{i}"
                    )
                
                # Bid 2
                st.markdown("**Bid 2 (Higher Cost):**")
                col1_bid2, col2_bid2 = st.columns(2)
                with col1_bid2:
                    gen['quantities'][1] = st.number_input(
                        "Quantity 2 (MW)", 
                        min_value=0, max_value=gen['max_capacity'] - gen['quantities'][0],
                        value=gen['quantities'][1],
                        key=f"gen_q2_{i}"
                    )
                with col2_bid2:
                    gen['prices'][1] = st.number_input(
                        "Price 2 ($/MWh)", 
                        min_value=gen['prices'][0], max_value=200.0,
                        value=float(gen['prices'][1]),
                        key=f"gen_p2_{i}"
                    )
                
                st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 🔵 Retailer Bids (Demand)")
        
        for i, ret in enumerate(st.session_state.retailers):
            with st.expander(f"Retailer: {ret['name']} (Bus {ret['bus'] + 1})", expanded=True):
                st.markdown('<div class="retailer-card">', unsafe_allow_html=True)
                
                # Bid 1
                st.markdown("**Bid 1 (Higher Price):**")
                col1_bid1, col2_bid1 = st.columns(2)
                with col1_bid1:
                    ret['quantities'][0] = st.number_input(
                        "Quantity 1 (MW)", 
                        min_value=0, max_value=500,
                        value=ret['quantities'][0],
                        key=f"ret_q1_{i}"
                    )
                with col2_bid1:
                    ret['prices'][0] = st.number_input(
                        "Price 1 ($/MWh)", 
                        min_value=0.0, max_value=200.0,
                        value=float(ret['prices'][0]),
                        key=f"ret_p1_{i}"
                    )
                
                # Bid 2
                st.markdown("**Bid 2 (Lower Price):**")
                col1_bid2, col2_bid2 = st.columns(2)
                with col1_bid2:
                    ret['quantities'][1] = st.number_input(
                        "Quantity 2 (MW)", 
                        min_value=0, max_value=500,
                        value=ret['quantities'][1],
                        key=f"ret_q2_{i}"
                    )
                with col2_bid2:
                    ret['prices'][1] = st.number_input(
                        "Price 2 ($/MWh)", 
                        min_value=0.0, max_value=ret['prices'][0],
                        value=float(ret['prices'][1]),
                        key=f"ret_p2_{i}"
                    )
                
                st.markdown('</div>', unsafe_allow_html=True)

def _update_bus_configuration(edited_buses_df):
    """Update bus configuration and regenerate generators/retailers lists"""
    try:
        # Update network bus configuration
        for i, row in edited_buses_df.iterrows():
            bus_idx = int(row['Bus']) - 1  # Convert to 0-based index
            
            # Update bus properties
            st.session_state.network['buses'][bus_idx]['type'] = row['Type']
            st.session_state.network['buses'][bus_idx]['v_magnitude'] = row['V_nom']
            
            # Parse generators and retailers from comma-separated strings
            generators = []
            if row['Generators'] and row['Generators'].strip():
                generators = [g.strip() for g in row['Generators'].split(',') if g.strip()]
            
            retailers = []
            if row['Retailers'] and row['Retailers'].strip():
                retailers = [r.strip() for r in row['Retailers'].split(',') if r.strip()]
            
            # Update bus assignments
            st.session_state.network['buses'][bus_idx]['generators'] = generators
            st.session_state.network['buses'][bus_idx]['retailers'] = retailers
        
        # Regenerate generator and retailer lists based on new bus assignments
        _regenerate_generators_list()
        _regenerate_retailers_list()
        
        # Clear existing results to force re-analysis
        st.session_state.market_results = None
        st.session_state.powerflow_results = None
        
        st.success("✅ Bus configuration updated successfully!")
        st.info("🔄 Market and power flow results cleared - please re-run analysis")
        
    except Exception as e:
        st.error(f"Error updating bus configuration: {str(e)}")

def _regenerate_generators_list():
    """Regenerate generators list based on current bus assignments"""
    new_generators = []
    existing_gen_dict = {gen['name']: gen for gen in st.session_state.generators}
    
    # Collect all generator names from all buses
    all_generator_names = set()
    for bus_idx, bus in enumerate(st.session_state.network['buses']):
        for gen_name in bus.get('generators', []):
            all_generator_names.add((gen_name, bus_idx))
    
    # Create generators based on bus assignments
    for gen_name, bus_idx in all_generator_names:
        if gen_name in existing_gen_dict:
            # Update existing generator with new bus assignment
            existing_gen = existing_gen_dict[gen_name].copy()
            existing_gen['bus'] = bus_idx
            new_generators.append(existing_gen)
        else:
            # Create new generator with default parameters
            new_generators.append({
                'name': gen_name,
                'bus': bus_idx,
                'quantities': [100, 150],  # Default bid quantities
                'prices': [30, 45],        # Default bid prices
                'min_capacity': 50,
                'max_capacity': 250
            })
    
    st.session_state.generators = new_generators

def _regenerate_retailers_list():
    """Regenerate retailers list based on current bus assignments"""
    new_retailers = []
    existing_ret_dict = {ret['name']: ret for ret in st.session_state.retailers}
    
    # Collect all retailer names from all buses
    all_retailer_names = set()
    for bus_idx, bus in enumerate(st.session_state.network['buses']):
        for ret_name in bus.get('retailers', []):
            all_retailer_names.add((ret_name, bus_idx))
    
    # Create retailers based on bus assignments
    for ret_name, bus_idx in all_retailer_names:
        if ret_name in existing_ret_dict:
            # Update existing retailer with new bus assignment
            existing_ret = existing_ret_dict[ret_name].copy()
            existing_ret['bus'] = bus_idx
            new_retailers.append(existing_ret)
        else:
            # Create new retailer with default parameters
            new_retailers.append({
                'name': ret_name,
                'bus': bus_idx,
                'quantities': [120, 100],  # Default bid quantities
                'prices': [50, 35]         # Default bid prices
            })
    
    st.session_state.retailers = new_retailers

def render_network_topology():
    """Render network topology visualization"""
    st.markdown("## 🔌 Network Topology")
    
    # Create network graph
    G = nx.Graph()
    
    # Add nodes
    for i, bus in enumerate(st.session_state.network['buses']):
        G.add_node(i, name=bus['name'], type=bus['type'])
    
    # Add edges
    edge_labels = {}
    for line in st.session_state.network['lines']:
        G.add_edge(line['from_bus'], line['to_bus'])
        edge_labels[(line['from_bus'], line['to_bus'])] = f"R={line['resistance']:.3f}\nX={line['reactance']:.3f}"
    
    # Create layout
    pos = nx.spring_layout(G, seed=42, k=2, iterations=50)
    
    # Create plotly figure
    fig = go.Figure()
    
    # Add edges
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        
        fig.add_trace(go.Scatter(
            x=[x0, x1, None], 
            y=[y0, y1, None],
            mode='lines',
            line=dict(width=2, color='gray'),
            hoverinfo='none',
            showlegend=False
        ))
    
    # Add nodes
    node_colors = {'Slack': 'red', 'PV': 'blue', 'PQ': 'green'}
    
    for node in G.nodes():
        x, y = pos[node]
        bus = st.session_state.network['buses'][node]
        
        # Node info
        generators = bus.get('generators', [])
        retailers = bus.get('retailers', [])
        info_text = f"Bus {node + 1}: {bus['name']}<br>"
        info_text += f"Type: {bus['type']}<br>"
        if generators:
            info_text += f"Generators: {', '.join(generators)}<br>"
        if retailers:
            info_text += f"Retailers: {', '.join(retailers)}"
        
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode='markers+text',
            marker=dict(
                size=30,
                color=node_colors.get(bus['type'], 'gray'),
                line=dict(width=2, color='white')
            ),
            text=[f"Bus {node + 1}"],
            textposition="middle center",
            textfont=dict(color="white", size=10),
            hovertext=info_text,
            hoverinfo='text',
            name=bus['type'],
            showlegend=False
        ))
    
    fig.update_layout(
        title="Power System Network Topology",
        showlegend=True,
        hovermode='closest',
        margin=dict(b=20,l=5,r=5,t=40),
        annotations=[
            dict(
                text="Red=Slack, Blue=PV, Green=PQ",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.005, y=-0.002,
                xanchor='left', yanchor='bottom',
                font=dict(size=12)
            )
        ],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Network data table
    st.markdown("### 📊 Network Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Bus Data:**")
        bus_data = []
        for i, bus in enumerate(st.session_state.network['buses']):
            bus_data.append({
                'Bus': i + 1,
                'Name': bus['name'],
                'Type': bus['type'],
                'V_nom': bus['v_magnitude'],
                'Generators': ', '.join(bus.get('generators', [])) or '',
                'Retailers': ', '.join(bus.get('retailers', [])) or ''
            })
        
        df_buses = pd.DataFrame(bus_data)
        
        # Create editable bus dataframe
        edited_buses = st.data_editor(
            df_buses,
            column_config={
                'Bus': st.column_config.NumberColumn(
                    'Bus #',
                    disabled=True,
                    help='Bus number (cannot be edited)'
                ),
                'Name': st.column_config.TextColumn(
                    'Bus Name',
                    disabled=True,
                    help='Bus name (cannot be edited)'
                ),
                'Type': st.column_config.SelectboxColumn(
                    'Bus Type',
                    options=['Slack', 'PV', 'PQ'],
                    help='Bus type: Slack (reference), PV (generator), PQ (load)'
                ),
                'V_nom': st.column_config.NumberColumn(
                    'V_nom (pu)',
                    min_value=0.9,
                    max_value=1.1,
                    step=0.01,
                    format="%.3f",
                    help='Nominal voltage magnitude in per unit'
                ),
                'Generators': st.column_config.TextColumn(
                    'Generators',
                    help='Comma-separated list of generators (e.g., Gen1, Gen2)'
                ),
                'Retailers': st.column_config.TextColumn(
                    'Retailers',
                    help='Comma-separated list of retailers'
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Check for changes and update bus data
        if not edited_buses.equals(df_buses):
            st.info("📝 Bus data has been modified")
            
            # Update button
            if st.button("🔄 Update Bus Configuration", type="primary"):
                _update_bus_configuration(edited_buses)
                st.rerun()
    
    with col2:
        st.markdown("**Line Data:**")
        line_data = []
        for i, line in enumerate(st.session_state.network['lines']):
            line_data.append({
                'Line_ID': i,
                'From': line['from_bus'] + 1,
                'To': line['to_bus'] + 1,
                'R (pu)': line['resistance'],
                'X (pu)': line['reactance'],
                'B (pu)': line['susceptance'],
                'Rating (MW)': line['rating']
            })
        
        df_lines = pd.DataFrame(line_data)
        
        # Create editable dataframe
        edited_lines = st.data_editor(
            df_lines,
            column_config={
                'Line_ID': st.column_config.NumberColumn(
                    'Line ID',
                    disabled=True,
                    help='Line identifier (cannot be edited)'
                ),
                'From': st.column_config.NumberColumn(
                    'From Bus',
                    disabled=True,
                    help='From bus number (cannot be edited)'
                ),
                'To': st.column_config.NumberColumn(
                    'To Bus',
                    disabled=True,
                    help='To bus number (cannot be edited)'
                ),
                'R (pu)': st.column_config.NumberColumn(
                    'R (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line resistance in per unit'
                ),
                'X (pu)': st.column_config.NumberColumn(
                    'X (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line reactance in per unit'
                ),
                'B (pu)': st.column_config.NumberColumn(
                    'B (pu)',
                    min_value=0.0,
                    max_value=1.0,
                    step=0.001,
                    format="%.4f",
                    help='Line susceptance in per unit'
                ),
                'Rating (MW)': st.column_config.NumberColumn(
                    'Rating (MW)',
                    min_value=0,
                    max_value=1000,
                    step=10,
                    help='Line rating in MW'
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Update network data if changes are made
        if not edited_lines.equals(df_lines):
            st.info("📝 Line data has been modified")
            
            # Update button
            if st.button("💾 Update Line Data", type="primary"):
                # Update the network data with edited values
                for i, row in edited_lines.iterrows():
                    line_id = int(row['Line_ID'])
                    line = st.session_state.network['lines'][line_id]
                    line['resistance'] = float(row['R (pu)'])
                    line['reactance'] = float(row['X (pu)'])
                    line['susceptance'] = float(row['B (pu)'])
                    line['rating'] = int(row['Rating (MW)'])
                
                # Clear previous results since network changed
                st.session_state.powerflow_results = None
                st.session_state.optimal_dc_results = None
                st.session_state.dc_opf_powerflow_results = None
                
                st.success("✅ Line data updated successfully!")
                msg = ("ℹ️ Previous power flow results cleared. "
                       "Re-solve with new data.")
                st.info(msg)
                st.rerun()


def render_market_results():
    """Render market clearing results"""
    st.markdown("## 📈 Market Results")
    
    if not st.session_state.market_results:
        st.info("Solve the market first to see results.")
        return
    
    market_data = st.session_state.market_results
    
    # Market summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Market Price", f"${market_data['price']:.2f}/MWh")
        st.metric("Cleared Quantity", f"{market_data['quantity']:.1f} MW")
    with col2:
        total_gen = sum(market_data.get('generation_dispatch', {}).values())
        total_load = sum(market_data.get('demand_dispatch', {}).values())
        st.metric("Total Generation", f"{total_gen:.1f} MW")
        st.metric("Total Load", f"{total_load:.1f} MW")
    with col3:
        total_payment = sum(market_data.get('retailer_costs', {}).values())
        total_revenue = sum(market_data.get('generator_revenues', {}).values())
        st.metric("Total Payment (Load)", f"${total_payment:,.0f}")
        st.metric("Total Revenue (Gen)", f"${total_revenue:,.0f}")

    # Dispatch results
    colA, colB = st.columns(2)
    with colA:
        st.markdown("### 🔴 Generator Dispatch")
        gen_results = []
        for gen in st.session_state.generators:
            gen_name = gen['name']
            dispatch = market_data['generation_dispatch'].get(gen_name, 0)
            revenue = market_data['generator_revenues'].get(gen_name, 0)
            cap = gen.get('max_capacity', 0) or 0
            cf = (dispatch / cap * 100) if cap > 0 else 0.0
            gen_results.append({
                'Generator': gen_name,
                'Bus': gen['bus'] + 1,
                'Dispatch (MW)': f"{dispatch:.1f}",
                'Revenue ($)': f"{revenue:,.0f}",
                'Capacity Factor (%)': f"{cf:.1f}",
            })
        st.dataframe(pd.DataFrame(gen_results), use_container_width=True)
    with colB:
        st.markdown("### 🔵 Retailer Dispatch")
        ret_results = []
        for ret in st.session_state.retailers:
            ret_name = ret['name']
            dispatch = market_data['demand_dispatch'].get(ret_name, 0)
            cost = market_data['retailer_costs'].get(ret_name, 0)
            total_bid = sum(ret.get('quantities', []) or [])
            fill = (dispatch / total_bid * 100) if total_bid > 0 else 0.0
            ret_results.append({
                'Retailer': ret_name,
                'Bus': ret['bus'] + 1,
                'Dispatch (MW)': f"{dispatch:.1f}",
                'Cost ($)': f"{cost:,.0f}",
                'Fill Rate (%)': f"{fill:.1f}",
            })
        st.dataframe(pd.DataFrame(ret_results), use_container_width=True)


def render_dc_opf_results():
    """Render DC OPF results: LMPs, line flows vs limits, and diagnostics"""
    st.markdown("## ⚡ DC OPF Results")
    
    if st.session_state.optimal_dc_results is None:
        st.info("ℹ️ Run 'DC OPF' from the sidebar to see results here.")
        return
    
    optimal_data = st.session_state.optimal_dc_results
    network = st.session_state.network
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        total_cost = float(optimal_data.get('total_cost', 0) or 0)
        st.metric("Optimal Cost", f"${total_cost:,.0f}")
        total_gen = sum(optimal_data.get('generation_dispatch', {}).values())
        st.metric("Total Generation", f"{total_gen:.1f} MW")
    with col2:
        shadow_prices = optimal_data.get('shadow_prices', {}) or {}
        if shadow_prices:
            avg_lmp = float(np.mean(list(shadow_prices.values())))
        else:
            avg_lmp = float(optimal_data.get('average_lmp', 0) or 0)
        st.metric("Average LMPs", f"${avg_lmp:.2f}/MWh")
        total_load = sum(optimal_data.get('demand_dispatch', {}).values())
        st.metric("Total Load", f"{total_load:.1f} MW")
    with col3:
        spread = 0.0
        if shadow_prices:
            vals = list(shadow_prices.values())
            spread = max(vals) - min(vals)
        st.metric("LMP Spread", f"${spread:.2f}/MWh")
    
    # LMP table
    st.markdown("### 🏷️ Locational Marginal Prices (LMPs)")
    lmp_rows = []
    buses = network['buses']
    for idx, bus in enumerate(buses):
        bus_key = f"Bus {idx+1}"
        lmp = shadow_prices.get(bus_key, avg_lmp)
        lmp_rows.append({
            'Bus #': idx+1,
            'Bus Name': bus.get('name', bus_key),
            'LMP ($/MWh)': f"${float(lmp):.2f}"
        })
    if lmp_rows:
        df_lmps = pd.DataFrame(lmp_rows)
        st.dataframe(df_lmps, use_container_width=True)
    else:
        st.info("No LMPs available.")
    
    # Line flows
    st.markdown("### 🔌 Transmission Line Flows vs Limits")
    line_rows = []
    line_flows = optimal_data.get('line_flows', []) or []
    for lf in line_flows:
        # Handle both variants of stored line flow dicts
        from_bus = lf.get('from_bus')
        to_bus = lf.get('to_bus')
        # Normalize to 1-based for display if needed
        # Flow and limit
        flow_mw = float(lf.get('flow_mw', 0) or 0)
        limit_mw = lf.get('limit_mw', lf.get('thermal_limit', 0))
        limit_mw = float(limit_mw or 0)
        loading = lf.get('loading_percent')
        if loading is None and limit_mw > 0:
            loading = abs(flow_mw) / limit_mw * 100.0
        loading = float(loading or 0)
        status = "✅ Normal"
        if limit_mw > 0 and abs(flow_mw) >= 0.99 * limit_mw:
            status = "🚨 Congested"
        if from_bus is not None and to_bus is not None:
            try:
                fb = int(from_bus)
                tb = int(to_bus)
                # Solver stores 1-based; only bump if old 0-based values appear
                if fb == 0 or tb == 0:
                    fb += 1
                    tb += 1
                line_name = f"Line {fb}-{tb}"
            except Exception:
                line_name = f"Line {from_bus}-{to_bus}"
        else:
            line_name = "Line"
        line_rows.append({
            'Line': line_name,
            'Flow (MW)': f"{flow_mw:.1f}",
            'Limit (MW)': f"{limit_mw:.1f}",
            'Loading (%)': f"{loading:.1f}",
            'Status': status
        })
    if line_rows:
        df_lines = pd.DataFrame(line_rows)
        st.dataframe(df_lines, use_container_width=True)
    else:
        st.info("No line flow data available.")
    
    # Congestion summary
    congested = optimal_data.get('congested_lines', []) or []
    if congested:
        names = []
        for c in congested:
            if isinstance(c, dict):
                names.append(c.get('line', ''))
            else:
                names.append(str(c))
        names = [n for n in names if n]
        if names:
            st.error(f"Congested Lines: {', '.join(names)}")
    else:
        st.success("No active transmission constraints.")
    
    # DC OPF Solution: full mathematical formulation (moved here)
    with st.expander("📐 DC OPF Solution — click to view formulation with actual values"):
        solver = optimal_data.get('solver')
        if solver and hasattr(solver, 'display_mathematical_formulation'):
            solver.display_mathematical_formulation()
        else:
            st.info("Formulation unavailable.")

    # Diagnostics
    with st.expander("🔍 LMP Diagnostics", expanded=False):
        raw_duals = optimal_data.get('raw_duals', {}) or {}
        if not raw_duals and not shadow_prices:
            st.info("No diagnostics available.")
        else:
            diag_rows = []
            for idx, bus in enumerate(buses):
                key = f"Bus {idx+1}"
                raw = raw_duals.get(key, None)
                lmp = shadow_prices.get(key, None)
                diag_rows.append({
                    'Bus': key,
                    'Raw dual': f"{raw if raw is not None else ''}",
                    'LMP ($/MWh)': f"{lmp if lmp is not None else ''}",
                })
            st.dataframe(pd.DataFrame(diag_rows), use_container_width=True)
    # End DC OPF Results

def render_power_flow_results():
    """Render AC power flow results for market and DC OPF"""
    st.markdown("## ⚡ AC Power Flow Analysis")
    
    # Check what results are available
    has_market = st.session_state.market_results is not None
    has_dc_opf = st.session_state.optimal_dc_results is not None
    
    # Create two main sections for Market and DC OPF
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🏪 Market-Based AC Power Flow")
        
        if has_market:
            # Show market dispatch info
            market_gen = sum(
                st.session_state.market_results['generation_dispatch'].values()
            )
            market_demand = sum(
                st.session_state.market_results['demand_dispatch'].values()
            )
            st.info(
                f"📊 Market Dispatch: {market_gen:.1f} MW gen, "
                f"{market_demand:.1f} MW load"
            )
            
            # Market completed successfully
            st.success("✅ Market Clearing Completed")
            st.info(
                "ℹ️ Use 'Market vs DC OPF' tab to compare market and "
                "optimal solutions"
            )
        else:
            st.warning("⚠️ Run 'Only Market' first to get dispatch results")
    
    with col2:
        st.markdown("### ⚡ DC OPF Results")
        
        if has_dc_opf:
            # Show DC OPF dispatch info
            opf_gen = sum(
                st.session_state.optimal_dc_results[
                    'generation_dispatch'
                ].values()
            )
            opf_demand = sum(
                st.session_state.optimal_dc_results['demand_dispatch'].values()
            )
            st.info(
                f"📊 DC OPF Dispatch: {opf_gen:.1f} MW gen, "
                f"{opf_demand:.1f} MW load"
            )
            
            # DC OPF completed successfully
            st.success("✅ DC OPF Optimization Completed")
            st.info(
                "ℹ️ Use 'Market vs DC OPF' tab to compare market and "
                "optimal solutions"
            )
        else:
            st.warning("⚠️ Run 'DC OPF' first to get dispatch results")

def render_market_vs_optimal_comparison():
    """Render comparison between market clearing and DC OPF"""
    st.markdown("## 🔋 Only Market vs DC OPF Comparison")
    
    # Check if we have both results
    has_market = st.session_state.market_results is not None
    has_optimal = st.session_state.optimal_dc_results is not None
    
    if not has_market and not has_optimal:
        st.info("📊 Run both 'Solve Market' and 'DC OPF' to see comparison")
        return
    elif not has_market:
        st.warning("⚠️ Run 'Solve Market' first to enable comparison")
        return
    elif not has_optimal:
        st.warning("⚠️ Run 'DC OPF' to enable comparison")
        return
    
    market_data = st.session_state.market_results
    optimal_data = st.session_state.optimal_dc_results
    
    # Summary comparison
    st.markdown("### 📊 Summary Comparison")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 🏪 Market Clearing")
        st.metric("Market Price", f"${market_data['price']:.2f}/MWh")
        st.metric("Cleared Quantity", f"{market_data['quantity']:.1f} MW")
        market_cost = sum(market_data['retailer_costs'].values())
        st.metric("Total Payment", f"${market_cost:,.0f}")
    
    with col2:
        st.markdown("#### 🔋 DC OPF")
        st.metric("Optimal Cost", f"${optimal_data['total_cost']:.0f}")
        optimal_gen = sum(optimal_data['generation_dispatch'].values())
        optimal_load = sum(optimal_data['demand_dispatch'].values())
        st.metric("Total Generation", f"{optimal_gen:.1f} MW")
        st.metric("Total Load", f"{optimal_load:.1f} MW")
        
        # Calculate and display Average LMPs
        if optimal_data.get('shadow_prices'):
            avg_lmp = np.mean(list(optimal_data['shadow_prices'].values()))
        else:
            avg_lmp = optimal_data.get('system_lambda', 0)
        st.metric("Average LMPs", f"${avg_lmp:.2f}/MWh")
    
    with col3:
        st.markdown("#### 💰 Economic Impact")
        cost_difference = market_cost - optimal_data['total_cost']
        efficiency_loss = (
            (cost_difference / optimal_data['total_cost']) * 100
            if optimal_data['total_cost'] > 0 else 0
        )
        st.metric(
            "Cost Difference",
            f"${cost_difference:,.0f}",
            delta=f"{efficiency_loss:.1f}% loss",
        )
        
        # Power balance difference
        market_balance = market_data['quantity']
        optimal_balance = optimal_gen
        balance_diff = abs(market_balance - optimal_balance)
        st.metric("Power Difference", f"{balance_diff:.1f} MW")
    
    # Dispatch comparison
    st.markdown("### ⚡ Generation Dispatch Comparison")
    
    # Create comparison dataframe
    dispatch_comparison = []
    
    for gen in st.session_state.generators:
        gen_name = gen['name']
        market_dispatch = market_data['generation_dispatch'].get(gen_name, 0)
        optimal_dispatch = optimal_data['generation_dispatch'].get(gen_name, 0)
        difference = optimal_dispatch - market_dispatch
        
        dispatch_comparison.append({
            'Generator': gen_name,
            'Bus': gen['bus'] + 1,
            'Market (MW)': f"{market_dispatch:.1f}",
            'DC OPF (MW)': f"{optimal_dispatch:.1f}",
            'Difference (MW)': f"{difference:.1f}",
            'Change (%)': (
                f"{(difference/market_dispatch*100) if market_dispatch > 0 else 0:.1f}"
            )
        })
    
    df_dispatch = pd.DataFrame(dispatch_comparison)
    st.dataframe(df_dispatch, use_container_width=True)
    
    # Visual comparison
    fig_dispatch = go.Figure()
    
    generators = [gen['name'] for gen in st.session_state.generators]
    market_values = [
        market_data['generation_dispatch'].get(gen, 0)
        for gen in generators
    ]
    optimal_values = [
        optimal_data['generation_dispatch'].get(gen, 0)
        for gen in generators
    ]
    
    fig_dispatch.add_trace(go.Bar(
        name='Market Clearing',
        x=generators,
        y=market_values,
        marker_color='lightblue'
    ))
    
    fig_dispatch.add_trace(go.Bar(
        name='DC OPF',
        x=generators,
        y=optimal_values,
        marker_color='darkblue'
    ))
    
    fig_dispatch.update_layout(
        title="Generation Dispatch Comparison",
        xaxis_title="Generators",
        yaxis_title="Power Output (MW)",
        barmode='group'
    )
    
    st.plotly_chart(fig_dispatch, use_container_width=True)
    
    # Load dispatch comparison
    st.markdown("### 📈 Load Dispatch Comparison")
    
    load_comparison = []
    
    for ret in st.session_state.retailers:
        ret_name = ret['name']
        market_load = market_data['demand_dispatch'].get(ret_name, 0)
        optimal_load = optimal_data['demand_dispatch'].get(ret_name, 0)
        difference = optimal_load - market_load
        
        load_comparison.append({
            'Retailer': ret_name,
            'Bus': ret['bus'] + 1,
            'Market (MW)': f"{market_load:.1f}",
            'DC OPF (MW)': f"{optimal_load:.1f}",
            'Difference (MW)': f"{difference:.1f}",
            'Change (%)': (
                f"{(difference/market_load*100) if market_load > 0 else 0:.1f}"
            )
        })
    
    df_load = pd.DataFrame(load_comparison)
    st.dataframe(df_load, use_container_width=True)
    
    # LMP and Price Comparison
    st.markdown("### 💰 Price Analysis: Market vs DC OPF LMPs")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🏪 Market Clearing Price")
        market_price = market_data['price']
        st.metric("Uniform Market Price", f"${market_price:.2f}/MWh")
        st.info(
            "📝 **Single price** for all participants regardless of location"
        )
    
    with col2:
        st.markdown("#### ⚡ DC OPF Locational Marginal Prices")
        # Calculate Average LMPs
        if optimal_data.get('shadow_prices'):
            avg_lmp = np.mean(list(optimal_data['shadow_prices'].values()))
        else:
            avg_lmp = optimal_data.get('system_lambda', 0)
        st.metric("Average LMPs", f"${avg_lmp:.2f}/MWh")
        st.info(
            "📍 **Location-specific prices** reflecting transmission "
            "constraints"
        )
    
    # LMP details table
    st.markdown("#### 🏷️ Detailed LMP Analysis")
    
    # Calculate Average LMPs for fallback
    if optimal_data.get('shadow_prices'):
        avg_lmp = np.mean(list(optimal_data['shadow_prices'].values()))
    else:
        avg_lmp = optimal_data.get('system_lambda', 0)
    
    lmp_data = []
    for bus_idx, bus in enumerate(st.session_state.network['buses']):
        bus_name = f"Bus {bus_idx + 1}"
        nodal_lmp = optimal_data['shadow_prices'].get(bus_name, avg_lmp)
        price_diff = nodal_lmp - market_price
        
        # Identify what's connected to this bus
        generators_here = bus.get('generators', [])
        retailers_here = bus.get('retailers', [])
        
        lmp_data.append({
            'Bus': bus_idx + 1,
            'Bus Name': bus['name'],
            'Market Price ($/MWh)': f"${market_price:.2f}",
            'DC OPF LMP ($/MWh)': f"${nodal_lmp:.2f}",
            'Price Diff ($/MWh)': f"${price_diff:.2f}",
            'Generators': ', '.join(generators_here) or 'None',
            'Retailers': ', '.join(retailers_here) or 'None'
        })
    
    df_lmp = pd.DataFrame(lmp_data)
    st.dataframe(df_lmp, use_container_width=True)
    
    # Price insights
    max_lmp = max([
        float(optimal_data['shadow_prices'].get(f"Bus {i+1}", avg_lmp))
        for i in range(len(st.session_state.network['buses']))
    ])
    min_lmp = min([
        float(optimal_data['shadow_prices'].get(f"Bus {i+1}", avg_lmp))
        for i in range(len(st.session_state.network['buses']))
    ])
    lmp_spread = max_lmp - min_lmp
    
    st.markdown("#### 📊 Price Analysis Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Market Price", f"${market_price:.2f}/MWh")
        st.metric("Average LMPs", f"${avg_lmp:.2f}/MWh")
    
    with col2:
        st.metric("Max LMP", f"${max_lmp:.2f}/MWh")
        st.metric("Min LMP", f"${min_lmp:.2f}/MWh")
    
    with col3:
        st.metric("LMP Spread", f"${lmp_spread:.2f}/MWh")
        spread_pct = (
            (lmp_spread / market_price * 100) if market_price > 0 else 0
        )
        st.metric("Spread %", f"{spread_pct:.1f}%")
    
    if lmp_spread > 5:
        st.warning(
            "⚠️ **Significant LMP spread detected!** This indicates "
            "transmission congestion is affecting prices across the network."
        )
    elif lmp_spread > 1:
        st.info(
            "📊 **Moderate LMP variation** suggests some transmission "
            "constraints are active."
        )
    else:
        st.success(
            "✅ **Low LMP spread** indicates minimal transmission congestion."
        )
    
    # DC Power Flow Analysis: Voltage Angles & Line Flows
    st.markdown("### ⚡ DC Power Flow Analysis: Market vs DC OPF")
    
    # Check if we have both Market and DC OPF results
    has_market = st.session_state.market_results is not None
    has_dc_opf = st.session_state.optimal_dc_results is not None
    
    if has_market and has_dc_opf:
        # Calculate Market DC power flow for comparison
        market_dc_pf = calculate_market_dc_power_flow(
            st.session_state.market_results,
            st.session_state.network,
        )
        
        if market_dc_pf['solved']:
            # Show comparison between Market and DC OPF DC power flow results
            st.markdown("#### 📊 Voltage Angles Comparison")
            st.info(
                "💡 **Note:** In DC power flow, voltage magnitudes are assumed "
                "to be 1.0 pu at all buses. The key variables are voltage "
                "angles and line flows."
            )
            
            # Voltage angles comparison
            angle_comparison = []
            max_angle_diff = 0
            
            # Get DC OPF voltage angles from the stored results
            optimal_data = st.session_state.optimal_dc_results
            dcopf_angles = optimal_data.get('voltage_angles', {})
            
            for bus_name in [
                bus['name'] for bus in st.session_state.network['buses']
            ]:
                market_angle = market_dc_pf['voltage_angles'].get(
                    bus_name, 0.0
                )
                dcopf_angle = dcopf_angles.get(bus_name, 0.0)
                angle_diff = abs(dcopf_angle - market_angle)
                max_angle_diff = max(max_angle_diff, angle_diff)
                
                angle_comparison.append({
                    'Bus': bus_name,
                    'Market Angle (rad)': f"{market_angle:.4f}",
                    'DC OPF Angle (rad)': f"{dcopf_angle:.4f}",
                    'Difference (rad)': f"{angle_diff:.4f}",
                    'Difference (deg)': f"{np.degrees(angle_diff):.2f}°"
                })
            
            df_angles = pd.DataFrame(angle_comparison)
            st.dataframe(df_angles, use_container_width=True)
            
            # Line flows comparison
            st.markdown("#### 🔌 Transmission Line Flows Comparison")
            
            flow_comparison = []
            max_flow_diff = 0
            
            # Get DC OPF line flows
            dcopf_flows = optimal_data['line_flows']
            market_flows = market_dc_pf['line_flows']
            
            for line_name in market_flows.keys():
                market_flow = market_flows.get(line_name, 0.0)
                dcopf_flow = dcopf_flows.get(line_name, 0.0)
                flow_diff = abs(dcopf_flow - market_flow)
                max_flow_diff = max(max_flow_diff, flow_diff)
                
                # Check if line is congested in DC OPF
                congestion_status = "✅ Normal"
                if optimal_data['congested_lines']:
                    congested_line_names = [
                        line_data['line'] if isinstance(line_data, dict)
                        else line_data
                        for line_data in optimal_data['congested_lines']
                    ]
                    if line_name in congested_line_names:
                        congestion_status = "🚨 Congested"
                
                flow_comparison.append({
                    'Line': line_name,
                    'Market Flow (MW)': f"{market_flow:.1f}",
                    'DC OPF Flow (MW)': f"{dcopf_flow:.1f}",
                    'Difference (MW)': f"{flow_diff:.1f}",
                    'DC OPF Status': congestion_status
                })
            
            df_flows = pd.DataFrame(flow_comparison)
            st.dataframe(df_flows, use_container_width=True)
            
            # Analysis insights
            st.markdown("#### 🔍 Key Insights")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**📐 Voltage Angles:**")
                if max_angle_diff > 0.1:  # 0.1 rad ≈ 5.7 degrees
                    st.warning(
                        "⚠️ **Significant angle differences!** Max: "
                        f"{np.degrees(max_angle_diff):.1f}°"
                    )
                    st.info(
                        "💡 Large angle differences indicate transmission "
                        "constraints significantly affect power flow patterns."
                    )
                else:
                    st.success(
                        "✅ **Similar angle profiles.** Max difference: "
                        f"{np.degrees(max_angle_diff):.1f}°"
                    )
                    st.info(
                        "💡 Small angle differences suggest minimal "
                        "transmission constraint impact."
                    )
            
            with col2:
                st.markdown("**⚡ Line Flows:**")
                if max_flow_diff > 10:  # 10 MW threshold
                    st.warning(
                        "⚠️ **Significant flow differences!** Max: "
                        f"{max_flow_diff:.1f} MW"
                    )
                    st.info(
                        "💡 Large flow differences show how optimal dispatch "
                        "redistributes power to minimize costs."
                    )
                else:
                    st.success(
                        "✅ **Similar flow patterns.** Max difference: "
                        f"{max_flow_diff:.1f} MW"
                    )
                    st.info(
                        "💡 Similar flows indicate market clearing "
                        "approximates optimal dispatch well."
                    )
            
            # Congestion analysis
            if optimal_data['congested_lines']:
                st.markdown("#### 🚨 Transmission Constraints Impact")
                st.error(
                    "**DC OPF identifies "
                    f"{len(optimal_data['congested_lines'])} congested line(s)**"
                )
                st.info(
                    "💡 **Educational Point:** Congested lines in DC OPF show "
                    "where transmission capacity limits optimal economic "
                    "dispatch, leading to different flows compared to "
                    "unconstrained market clearing."
                )
            else:
                st.success(
                    "✅ **No transmission constraints active in DC OPF**"
                )
                st.info(
                    "💡 **Educational Point:** No congestion means the "
                    "transmission network can support optimal economic "
                    "dispatch without physical limitations."
                )
        
        else:
            st.error(
                "❌ Market DC power flow calculation failed. Cannot perform "
                "comparison."
            )
    
    elif has_dc_opf and not has_market:
        st.info(
            "ℹ️ **Market results not available.** Run Market Clearing first "
            "to enable Market vs DC OPF comparison."
        )
        st.info(
            "💡 The comparison shows how transmission constraints affect "
            "voltage angles and line flows."
        )
    
    elif has_market and not has_dc_opf:
        st.info(
            "ℹ️ **DC OPF results not available.** Run DC OPF to enable "
            "transmission constraint analysis."
        )
    
    else:
        st.info(
            "📊 Run both 'Solve Market' and 'DC OPF' to see DC power flow "
            "comparison"
        )
        st.info(
            "💡 **What you'll see:** Voltage angles, line flows, and "
            "transmission constraint impacts."
        )
    
    # Transmission analysis
    if optimal_data['congested_lines']:
        st.markdown("### 🚨 Transmission Constraints Impact")
        
        # Format congested lines properly
        if isinstance(optimal_data['congested_lines'][0], dict):
            # If congested_lines contains dictionaries
            congested_line_names = [
                line_data['line']
                for line_data in optimal_data['congested_lines']
            ]
        else:
            # If congested_lines contains strings
            congested_line_names = optimal_data['congested_lines']
        
        st.error(
            "**Congested Lines in Optimal Solution:** "
            f"{', '.join(congested_line_names)}"
        )
        
        # Show detailed congestion information
        if isinstance(optimal_data['congested_lines'][0], dict):
            st.markdown("#### 📊 Detailed Congestion Analysis")
            congestion_data = []
            for line_data in optimal_data['congested_lines']:
                congestion_data.append({
                    'Line': line_data['line'],
                    'Flow (MW)': f"{line_data['flow']:.1f}",
                    'Limit (MW)': f"{line_data['limit']:.1f}",
                    'Loading (%)': f"{line_data['loading']:.1f}%"
                })
            
            if congestion_data:
                df_congestion = pd.DataFrame(congestion_data)
                st.dataframe(df_congestion, use_container_width=True)
        
        st.markdown("""
        **Why Market and Optimal Results Differ:**
        - 🔴 **Market clearing ignores transmission constraints**
        - 🔵 **DC OPF respects line thermal limits**
        - ⚡ **Transmission congestion forces different dispatch patterns**
        - 💰 **Results in higher system costs but maintains reliability**
        """)
    else:
        st.success("✅ No transmission congestion in optimal solution")
        if abs(cost_difference) > 1000:
            st.info("""
            **Difference despite no congestion may be due to:**
            - Different objective functions (market price vs total cost)
            - Bidding strategy effects vs pure cost optimization
            - Load matching differences between approaches
            """)
    
    # Economic insights
    st.markdown("### 💡 Economic & Engineering Insights")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🏪 Market Clearing Characteristics")
        st.markdown("""
        - **Price-based dispatch** using submitted bids
        - **Single clearing price** for all participants
        - **Does not consider** transmission constraints
        - **Market efficiency** depends on bidding strategies
        - **May result in infeasible** power flows
        """)
        
        if efficiency_loss > 10:
            st.warning(f"⚠️ High efficiency loss: {efficiency_loss:.1f}%")
        elif efficiency_loss > 5:
            st.info(f"📊 Moderate efficiency loss: {efficiency_loss:.1f}%")
        else:
            st.success(f"✅ Low efficiency loss: {efficiency_loss:.1f}%")
    
    with col2:
        st.markdown("#### 🔋 DC OPF Characteristics")
        st.markdown("""
        - **Cost-based dispatch** using generator costs
        - **Minimizes total system cost**
        - **Respects transmission** thermal limits
        - **Ensures feasible** power flows
        - **May require** out-of-merit dispatch
        """)
        
        # Shadow prices (Locational Marginal Prices)
        if optimal_data['shadow_prices']:
            st.markdown("**🎯 Locational Marginal Prices (LMPs):**")
            for bus, price in optimal_data['shadow_prices'].items():
                if price != 0:
                    st.write(f"   • {bus}: ${price:.2f}/MWh")
    
    # Key takeaways
    st.markdown("### 🎯 Key Takeaways")
    
    if efficiency_loss > 5:
        st.error(
            "**🚨 Significant Economic Impact Detected!**\n\n"
            f"The market clearing approach results in {efficiency_loss:.1f}% "
            "higher costs compared to the DC OPF solution. This demonstrates:"
            "\n\n1. **Importance of transmission constraints** in market design"
            "\n2. **Need for locational pricing** to reflect congestion"
            "\n3. **Value of coordinated optimization** vs. bilateral trading"
            "\n4. **Economic benefits** of centralized dispatch"
        )
    else:
        st.success(
            "**✅ Market and DC OPF Solutions Are Similar**\n\n"
            f"The efficiency loss is only {efficiency_loss:.1f}%, indicating:"
            "\n\n1. **No significant transmission constraints**"
            "\n2. **Market bids reflect actual costs** reasonably well"
            "\n3. **Current network capacity** is adequate"
            "\n4. **Market mechanism** works efficiently for this case"
        )
    
    # Recommendations
    st.markdown("#### 🔧 Recommendations")
    
    if optimal_data['congested_lines']:
        st.markdown("""
        **For Congested System:**
        - Implement locational marginal pricing (LMP)
        - Consider transmission expansion planning
        - Use security-constrained economic dispatch
        - Monitor generator bidding strategies
        """)
    else:
        st.markdown("""
        **For Uncongested System:**
        - Monitor for future congestion with load growth
        - Validate that market bids reflect true costs
        - Consider demand response programs
        - Plan transmission upgrades proactively
        """)


def main():
    """Main application function"""
    initialize_session_state()
    
    # Header
    st.markdown(
        '<h1 class="main-header">⚡ Double-Sided Electricity Market '
        'Dashboard</h1>',
        unsafe_allow_html=True,
    )
    
    st.markdown("""
    <div class="problem-box">
    <h3>🎯 Learning Objectives</h3>
    <p>This dashboard demonstrates:</p>
    <ul>
    <li><strong>Double-sided electricity markets</strong> with generator
    supply and retailer demand bids</li>
    <li><strong>Market clearing mechanism</strong> finding equilibrium
    price and quantity</li>
    <li><strong>Transmission network constraints</strong> using AC power
    flow analysis</li>
    <li><strong>Congestion management</strong> and system operational
    limits</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    render_sidebar()
    
    # Main content using tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🏪 Market Setup",
        "🔌 Network Topology",
        "📈 Market Results",
        "⚡ DC OPF Results",
        "🔋 Market vs DC OPF",
        "📚 Theory & Concepts"
    ])
    
    with tab1:
        render_market_setup()
    
    with tab2:
        render_network_topology()
    
    with tab3:
        render_market_results()
    
    with tab4:
        render_dc_opf_results()
    
    with tab5:
        render_market_vs_optimal_comparison()
    
    with tab6:
        st.markdown("## 📚 Theory and Concepts")
        
        st.markdown("""
        
                **Market Structure:**
                        - **Generators** submit supply bids (quantity, price) in
                            ascending price order
                - **Retailers/Load** submit demand bids (quantity, price) in
                    descending price order
                        - **Market operator** finds clearing price where supply meets
                            demand
        
        **Key Concepts:**
                        - **Market Clearing Price**: Single price paid by all buyers
                            and received by all sellers
                - **Economic Dispatch**: Generators dispatched in merit order
                    (lowest cost first)
                        - **Consumer Surplus**: Benefit to buyers paying less than
                            their bid price
                        - **Producer Surplus**: Benefit to sellers receiving more than
                            their bid price
        
        ### ⚡ AC Power Flow Analysis
        
        **Power Flow Equations:**
        - **Active Power**: P = V²G - VV'(G cos θ + B sin θ)
        - **Reactive Power**: Q = -V²B - VV'(G sin θ - B cos θ)
        - **Newton-Raphson Method**: Iterative solution of nonlinear equations
        
        **System Constraints:**
        - **Voltage Limits**: Typically 0.95 ≤ V ≤ 1.05 per unit
        - **Thermal Limits**: Line flows ≤ thermal rating
        - **Power Balance**: Generation = Load + Losses at each bus
        
        ### 🚦 Congestion Management
        
        **Congestion occurs when:**
        - Transmission lines approach thermal limits (>90% loading)
        - Voltage constraints are violated
        - System stability margins are exceeded
        
        **Market Impact:**
        - **Congestion costs**: Additional payments to manage constraints
        - **Locational pricing**: Different prices at different locations
        - **Re-dispatch**: Changing generation to relieve congestion
        """)
        
        # Interactive quiz section
        st.markdown("### 🧠 Quick Quiz")
        
        quiz_col1, quiz_col2 = st.columns(2)
        
        with quiz_col1:
            st.markdown(
                "**Question 1:** What happens to market price when demand "
                "increases?"
            )
            q1_answer = st.radio(
                "Choose the best answer:",
                [
                    "Price decreases",
                    "Price increases",
                    "Price stays the same",
                    "Cannot determine",
                ],
                key="q1"
            )
            
            if st.button("Show Answer 1"):
                if q1_answer == "Price increases":
                    st.success(
                        "✅ Correct! Higher demand shifts the demand curve "
                        "right, increasing equilibrium price."
                    )
                else:
                    st.error(
                        "❌ Incorrect. Higher demand typically increases "
                        "market clearing price."
                    )
        
        with quiz_col2:
            st.markdown(
                "**Question 2:** What causes transmission congestion?"
            )
            q2_answer = st.radio(
                "Choose the best answer:",
                [
                    "Low demand",
                    "High line impedance",
                    "Line flow exceeding thermal limit",
                    "Low generation",
                ],
                key="q2"
            )
            
            if st.button("Show Answer 2"):
                if q2_answer == "Line flow exceeding thermal limit":
                    st.success(
                        "✅ Correct! Congestion occurs when power flow "
                        "approaches or exceeds line thermal limits."
                    )
                else:
                    st.error(
                        "❌ Incorrect. Congestion is primarily caused by "
                        "thermal limit violations."
                    )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
    <p><strong>Double-Sided Electricity Market &amp; Power Flow
    Dashboard</strong></p>
    <p>Demonstrating Market Clearing • Power Flow • Congestion Analysis</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
