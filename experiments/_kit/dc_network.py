"""Shared DC network page for week 8.

Extracted from week8_pf_auction.py (its module-level body and main(),
minus the tab block at lines 2571-2701) on 2026-08-12. The six
double-sided-market experiments -- market setup, network topology,
market results, DC OPF results, market vs DC OPF, and power flow
theory -- each render this page plus their own tab body.
"""
from typing import Callable

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional  # noqa: F401
import networkx as nx
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
"""

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

def preamble() -> None:
    """Everything week 8's main() did before drawing its tabs."""
    initialize_session_state()
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

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


def postamble() -> None:
    """Everything week 8's main() did after its tabs."""
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
    <p><strong>Double-Sided Electricity Market &amp; Power Flow
    Dashboard</strong></p>
    <p>Demonstrating Market Clearing • Power Flow • Congestion Analysis</p>
    </div>
    """, unsafe_allow_html=True)


def page(tab_body: Optional[Callable[[], None]] = None) -> None:
    """Render the shared DC network page around the caller's own tab body.

    ``tab_body`` is invoked at the point where week8_pf_auction.py rendered
    its ``st.tabs`` block, so the footer below it still appears after it, as
    it does today.
    """
    preamble()
    if tab_body is not None:
        tab_body()
    postamble()
