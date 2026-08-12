"""Only-market versus DC OPF comparison.

Extracted from week8_pf_auction.py (render_market_vs_optimal_comparison,
tab 5) on 2026-08-12. The CSS, session state, sidebar and footer shared
with the other DC network experiments live in
experiments/_kit/dc_network.py.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional  # noqa: F401
import networkx as nx
import warnings
warnings.filterwarnings('ignore')

from experiments._kit import dc_network
from experiments._kit.dc_network import calculate_market_dc_power_flow

STATE_GROUP = "dc_network"


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

def _tab_body() -> None:
    render_market_vs_optimal_comparison()


def render() -> None:
    dc_network.page(_tab_body)
