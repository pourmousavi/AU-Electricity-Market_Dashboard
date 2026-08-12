"""Weak Duality Cases.

Extracted from week6_duality.py (tab 2, lines 412-436) on 2026-08-12. The page
body it shares with the other two duality experiments lives in
experiments/_kit/duality.py."""

import streamlit as st

from experiments._kit import duality

STATE_GROUP = "duality"


def _tab_body(prob_type: str) -> None:
    st.subheader("Cases Where Strong Duality Fails")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("**Case 1: Unbounded Primal**")
        st.markdown("""
        - Primal objective → ∞ (max) or -∞ (min)
        - Dual problem becomes infeasible
        - No finite optimal solutions exist
        """)
        
        st.markdown("**Example:** Try the 'Unbounded Primal' example above")
        
    with col2:
        st.markdown("**Case 2: Infeasible Primal**")
        st.markdown("""
        - Primal has no feasible solution
        - Dual becomes unbounded
        - Constraints are contradictory
        """)
        
        st.markdown("**Example:** Try the 'Infeasible Primal' example above")


def render() -> None:
    duality.page(_tab_body)
