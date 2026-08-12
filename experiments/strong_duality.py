"""Strong Duality.

Extracted from week6_duality.py (tab 1, lines 394-411) on 2026-08-12. The page
body it shares with the other two duality experiments lives in
experiments/_kit/duality.py."""

import streamlit as st

from experiments._kit import duality

STATE_GROUP = "duality"


def _tab_body(prob_type: str) -> None:
    st.subheader("Strong Duality")
    st.markdown("""
    **Strong duality** occurs when both primal and dual problems have optimal solutions and their objective values are equal.
    
    **Mathematical condition:**
    """)
    st.latex(r"""
    f^* = g^* \quad \text{(Duality gap = 0)}
    """)
    
    st.markdown("""
    **When does strong duality hold?**
    - Linear programs with bounded feasible regions
    - Convex optimization problems satisfying constraint qualifications
    - Both primal and dual have finite optimal solutions
    """)


def render() -> None:
    duality.page(_tab_body)
