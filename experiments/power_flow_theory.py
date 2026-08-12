"""Power flow theory and concepts.

Extracted from week8_pf_auction.py (the inline body of tab 6, lines
2596-2701 of main()) on 2026-08-12. The CSS, session state, sidebar and
footer shared with the other DC network experiments live in
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

STATE_GROUP = "dc_network"


def _tab_body() -> None:
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


def render() -> None:
    dc_network.page(_tab_body)
