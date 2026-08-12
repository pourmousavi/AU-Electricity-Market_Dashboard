"""Double-sided market setup.

Extracted from week8_pf_auction.py (render_market_setup, tab 1) on
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

def _tab_body() -> None:
    render_market_setup()


def render() -> None:
    dc_network.page(_tab_body)
