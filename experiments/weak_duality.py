"""Weak Duality Cases.

Extracted from week6_duality.py (tab 2, lines 412-436) on 2026-08-12. The page
body it shares with the other two duality experiments lives in
experiments/_kit/duality.py.

Where strong_duality shows the gap closed at the optimum, this experiment lets a
student pick any feasible x and any feasible λ and watch the gap that separates
them — the inequality the page used to only assert."""

import plotly.graph_objects as go
import streamlit as st

from experiments._kit import duality

# Own group: this experiment opens on its own worked example and its own
# sandwich picks, which a sibling's leftover slider values would overwrite.
STATE_GROUP = "duality.weak"

DEFAULTS = duality.STANDARD

PRESETS = {
    duality.SANDWICH_NAME: duality.STANDARD,
    duality.UNBOUNDED_NAME: duality.UNBOUNDED_PRIMAL,
    duality.INFEASIBLE_NAME: duality.INFEASIBLE_PRIMAL,
}

# Deliberately not the optimum: (1, 1) and (2, 2) are both feasible for the
# standard example, so the page opens with a gap of 15 already on screen. An
# optimal seed would show 0.000000 and demonstrate nothing.
PICK_DEFAULTS = {"weak_x1": 1.0, "weak_x2": 1.0, "weak_l1": 2.0, "weak_l2": 2.0}


def _rows_ok(sol: duality.Solution, x, primal: bool):
    """Which rows the pick satisfies, and the text for the ones it does not."""
    failures = []
    for i in range(2):
        if primal:
            lhs = sol.A[i][0] * x[0] + sol.A[i][1] * x[1]
            ok = lhs <= sol.d[i] + 1e-9 if sol.maximising else lhs >= sol.d[i] - 1e-9
            sign = "≤" if sol.maximising else "≥"
            if not ok:
                failures.append(f"row {i + 1}: {lhs:.2f} {sign} {sol.d[i]:.2f} is false")
        else:
            lhs = sol.A[0][i] * x[0] + sol.A[1][i] * x[1]
            ok = lhs >= sol.c[i] - 1e-9 if sol.maximising else lhs <= sol.c[i] + 1e-9
            sign = "≥" if sol.maximising else "≤"
            if not ok:
                failures.append(f"dual row {i + 1}: {lhs:.2f} {sign} {sol.c[i]:.2f} is false")
    if any(v < -1e-9 for v in x):
        failures.append("the non-negativity requirement")
    return failures


def _number_line(low_label, low, opt, high_label, high) -> go.Figure:
    """The sandwich: the two picks either side of the optimum, gap annotated."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[low, high], y=[0, 0], mode="lines",
        line=dict(color="#836BFF", width=6), name="duality gap", hoverinfo="skip",
    ))
    for value, label, colour in ((low, low_label, "#140F50"), (high, high_label, "#836BFF")):
        fig.add_trace(go.Scatter(
            x=[value], y=[0], mode="markers+text", text=[f"{label}<br>{value:.3f}"],
            textposition="bottom center", marker=dict(size=16, color=colour),
            name=label,
        ))
    if opt is not None:
        fig.add_trace(go.Scatter(
            x=[opt], y=[0], mode="markers+text", text=[f"optimum<br>{opt:.3f}"],
            textposition="top center",
            marker=dict(size=18, color="#F8EFE0", symbol="diamond",
                        line=dict(color="#140F50", width=2)),
            name="optimum",
        ))
    fig.add_annotation(x=(low + high) / 2, y=0.35, showarrow=False,
                       text=f"<b>gap = {abs(high - low):.3f}</b>")
    fig.update_layout(
        height=240, showlegend=False, margin=dict(l=20, r=20, t=20, b=20),
        yaxis=dict(visible=False, range=[-1, 1]), xaxis=dict(title="objective value"),
    )
    return fig


def _panel(sol: duality.Solution) -> None:
    """Pick any feasible pair and watch the gap that weak duality guarantees."""
    st.subheader("The weak duality sandwich: pick any feasible pair")

    for key, value in PICK_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    relation = "≤" if sol.maximising else "≥"
    st.markdown(
        f"Weak duality says **cᵀx {relation} dᵀλ** for *every* feasible pair — not "
        "just the optimal one. Pick any x and any λ below and watch the two values "
        "close on the optimum from either side."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Your primal pick, x**")
        x = (st.number_input("x₁", step=0.5, key="weak_x1"),
             st.number_input("x₂", step=0.5, key="weak_x2"))
    with col2:
        st.markdown("**Your dual pick, λ**")
        lam = (st.number_input("λ₁", step=0.5, key="weak_l1"),
               st.number_input("λ₂", step=0.5, key="weak_l2"))

    x_fails = _rows_ok(sol, x, primal=True)
    lam_fails = _rows_ok(sol, lam, primal=False)

    if x_fails:
        st.error("❌ Your x is **not feasible** — " + "; ".join(x_fails))
    if lam_fails:
        st.error("❌ Your λ is **not feasible** — " + "; ".join(lam_fails))
    if x_fails or lam_fails:
        st.info(
            "Weak duality says nothing about infeasible picks. Move them back "
            "inside the feasible region to see the sandwich."
        )
        return

    cx = sol.c[0] * x[0] + sol.c[1] * x[1]
    dl = sol.d[0] * lam[0] + sol.d[1] * lam[1]
    low, low_label, high, high_label = (
        (cx, "cᵀx (your x)", dl, "dᵀλ (your λ)") if sol.maximising
        else (dl, "dᵀλ (your λ)", cx, "cᵀx (your x)")
    )

    st.plotly_chart(_number_line(low_label, low, sol.f, high_label, high),
                    width="stretch")

    gap = abs(dl - cx)
    holds = cx <= dl + 1e-9 if sol.maximising else cx >= dl - 1e-9
    if not holds:
        st.error(
            f"cᵀx = {cx:.3f} and dᵀλ = {dl:.3f} break {relation} — that cannot "
            "happen for a feasible pair, so one of the checks above is wrong."
        )
    elif gap < 1e-6:
        st.success(
            "✅ Gap 0.000: both picks are optimal. This is the one pair where "
            "weak duality is tight — which is strong duality."
        )
    else:
        st.info(
            f"✓ cᵀx = {cx:.3f} {relation} dᵀλ = {dl:.3f}, gap **{gap:.3f}**. "
            "Every feasible λ bounds every feasible x, however far from optimal "
            "either one is."
        )


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

        st.markdown(f"**To see it:** load *{duality.UNBOUNDED_NAME}* above")

    with col2:
        st.markdown("**Case 2: Infeasible Primal**")
        st.markdown("""
        - Primal has no feasible solution
        - Dual becomes unbounded
        - Constraints are contradictory
        """)

        st.markdown(f"**To see it:** load *{duality.INFEASIBLE_NAME}* above")


def render() -> None:
    duality.page(_tab_body, defaults=DEFAULTS, presets=PRESETS, panel=_panel)
