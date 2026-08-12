"""Double-sided market results.

Extracted from week8_pf_auction.py (render_market_results, tab 3) on
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

def _tab_body() -> None:
    render_market_results()


def render() -> None:
    dc_network.page(_tab_body)
