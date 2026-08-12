"""DC optimal power flow results.

Extracted from week8_pf_auction.py (render_dc_opf_results, tab 4) on
2026-08-12. The CSS, session state, sidebar and footer shared with the
other DC network experiments live in experiments/_kit/dc_network.py.
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

STATE_GROUP = "dc_network"


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

def _tab_body() -> None:
    render_dc_opf_results()


def render() -> None:
    dc_network.page(_tab_body)
