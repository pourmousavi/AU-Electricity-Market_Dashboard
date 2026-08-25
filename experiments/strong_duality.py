"""Strong Duality.

Extracted from week6_duality.py (tab 1, lines 394-411) on 2026-08-12. The page
body it shares with the other two duality experiments lives in
experiments/_kit/duality.py.

This experiment opens on a case where the gap is zero and adds the mechanism
behind it: the complementary slackness table. Its sibling weak_duality opens on
the same rows but lets a student pick a NON-optimal feasible pair, where the
gap is visible."""

import streamlit as st

from experiments._kit import duality

# Own group: this experiment opens on its own worked example, which a sibling's
# leftover slider values would overwrite.
STATE_GROUP = "duality.strong"

DEFAULTS = duality.STANDARD

PRESETS = {
    duality.STANDARD_NAME: duality.STANDARD,
    duality.SLACK_NAME: duality.ONE_ROW_SLACK,
}


def _panel(sol: duality.Solution) -> None:
    """Why the gap is zero: every product of a slack and its price is zero."""
    st.subheader("Complementary Slackness: why the gap closes")

    if sol.x is None or sol.lam is None:
        st.info(
            "Complementary slackness needs both an optimal x and an optimal λ. "
            "This example has no such pair — try a worked example where both solve."
        )
        return

    st.markdown(
        "At the optimum every constraint is either **tight** (no slack) or has a "
        "**zero price**. Never both non-zero — that product is what the gap is "
        "made of, so a zero in every row means f\\* = g\\*."
    )

    rows = []
    for i, slack in enumerate(sol.primal_slack()):
        price = sol.lam[i]
        rows.append({
            "Row": f"Constraint {i + 1}:  dᵢ − Aᵢx*  ×  λᵢ*",
            "Slack": round(float(slack) + 0.0, 6),
            "Its multiplier": round(float(price) + 0.0, 6),
            "Product": round(float(slack * price) + 0.0, 6),
            "Reads as": "binds, so its price may be positive"
                        if abs(slack) < 1e-6 else "slack, so its price is zero",
        })
    for j, slack in enumerate(sol.dual_slack()):
        value = sol.x[j]
        rows.append({
            "Row": f"Dual row {j + 1}:  (Aᵀλ* − c)ⱼ  ×  xⱼ*",
            "Slack": round(float(slack) + 0.0, 6),
            "Its multiplier": round(float(value) + 0.0, 6),
            "Product": round(float(slack * value) + 0.0, 6),
            "Reads as": "binds, so x may be positive"
                        if abs(slack) < 1e-6 else "slack, so x is zero",
        })

    st.dataframe(rows, width="stretch", hide_index=True)

    worst = max(abs(row["Product"]) for row in rows)
    if worst < 1e-5:
        st.success(
            f"✅ Every product is zero (largest {worst:.2e}), so no gap can open: "
            f"f* = {sol.f:.3f} = g* = {sol.g:.3f}"
        )
    else:
        st.warning(f"⚠️ Largest product is {worst:.3e} — the gap is exactly this sum.")


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
    - Convex optimisation problems satisfying constraint qualifications
    - Both primal and dual have finite optimal solutions
    """)


def render() -> None:
    duality.page(_tab_body, defaults=DEFAULTS, presets=PRESETS, panel=_panel)
