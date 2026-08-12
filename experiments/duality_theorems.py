"""Duality Theorems.

Extracted from week6_duality.py (tab 3, lines 437-464) on 2026-08-12. The page
body it shares with the other two duality experiments lives in
experiments/_kit/duality.py."""

import streamlit as st

from experiments._kit import duality

STATE_GROUP = "duality"


def _tab_body(prob_type: str) -> None:
    st.subheader("Fundamental Duality Theorems")
    
    st.markdown("**Weak Duality Theorem:**")
    st.markdown("For any feasible solutions x (primal) and λ (dual):")
    
    if prob_type == "Maximize":
        st.latex(r"""
        c^T x \leq b^T \lambda \quad \text{(Maximization problems)}
        """)
    else:
        st.latex(r"""
        c^T x \geq b^T \lambda \quad \text{(Minimization problems)}
        """)
    
    st.markdown("**Strong Duality Theorem:**")
    st.markdown("If both problems have optimal solutions, then:")
    st.latex(r"""
    f^* = g^*
    """)
    
    st.markdown("**Complementary Slackness:**")
    st.markdown("At optimality, either a constraint is tight OR its dual variable is zero:")
    st.latex(r"""
    \lambda_i^* (b_i - A_i x^*) = 0 \quad \forall i
    """)


def render() -> None:
    duality.page(_tab_body)
