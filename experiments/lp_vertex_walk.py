"""LP Vertex Walk.

Why the optimum of a linear program sits at a vertex, and why it jumps from one
vertex to the next instead of sliding along an edge.

Two decision variables, so the whole thing is drawable in the plane. The user
rotates the objective by moving c1; the feasible region never moves. The
payload is the rotation angle at which an entire edge becomes optimal, because
that is the case a solver answers without mentioning that other answers exist.

Everything numeric lives in the pure functions at the top: numbers in, numbers
out, no Streamlit. The vertices are enumerated by intersecting every pair of
constraint boundaries, the two axes included, and discarding intersections that
break some other constraint. A solver is never asked for the polygon. SciPy's
HiGHS backend is then asked for the optimum independently, purely as a check on
the enumeration, and a disagreement is displayed rather than resolved.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.optimize import linprog

# Course palette. Navy and purple carry the lines, lavender fills the region.
NAVY = "#140F50"
PURPLE = "#836BFF"
BLUE = "#1448FF"
LIMESTONE = "#F8EFE0"
LAVENDER = "#ECE9FF"
SILVER = "#E9E6EE"

# Feasibility slack when testing a candidate vertex against every constraint.
# Absolute, and comfortably larger than the round-off of a 2x2 solve at the
# magnitudes this tool works in, but far smaller than any real violation.
FEAS_TOL = 1e-7

# Two vertices are tied when their objective values agree to this RELATIVE
# tolerance. Never test c1 == 30: the tie points move the moment a constraint
# changes, and a hard-coded pair of angles would then be silently wrong.
TIE_REL_TOL = 1e-7

# Agreement required between the enumerated optimum and the HiGHS optimum.
SOLVER_REL_TOL = 1e-6


@dataclass(frozen=True)
class Row:
    """One constraint, a1*x1 + a2*x2 <= b."""
    a1: float
    a2: float
    b: float


def row_label(row: Row) -> str:
    """A constraint written the way it would be written on the board."""
    parts: list[str] = []
    for coef, name in ((row.a1, "x₁"), (row.a2, "x₂")):
        if abs(coef) < 1e-12:
            continue
        body = name if abs(abs(coef) - 1) < 1e-12 else f"{abs(coef):g}{name}"
        if not parts:
            parts.append(f"-{body}" if coef < 0 else body)
        else:
            parts.append(f"{'-' if coef < 0 else '+'} {body}")
    lhs = " ".join(parts) if parts else "0"
    return f"{lhs} ≤ {row.b:g}"


AXIS_ROWS = (Row(-1.0, 0.0, 0.0), Row(0.0, -1.0, 0.0))
AXIS_LABELS = ("x₁ ≥ 0", "x₂ ≥ 0")


def all_rows(constraints: list[Row]) -> tuple[list[Row], list[str]]:
    """Structural constraints plus the two non-negativity rows, with labels.

    The axes are constraints like any other. They have to be in the pair
    enumeration or (0, 0), (8, 0) and (0, 12) are not vertices.
    """
    rows = list(constraints) + list(AXIS_ROWS)
    labels = [row_label(r) for r in constraints] + list(AXIS_LABELS)
    return rows, labels


def enumerate_vertices(
    constraints: list[Row],
) -> tuple[list[tuple[float, float]], list[tuple[str, ...]]]:
    """Every vertex of the feasible region, with the constraints active there.

    Solve each pair of boundary equations, throw away the pairs that are
    parallel, then throw away the intersections that violate some constraint.
    What survives is exactly the vertex set.
    """
    rows, labels = all_rows(constraints)
    found: dict[tuple[float, float], tuple[float, float]] = {}

    for i, j in combinations(range(len(rows)), 2):
        a = np.array([[rows[i].a1, rows[i].a2], [rows[j].a1, rows[j].a2]], float)
        if abs(np.linalg.det(a)) < 1e-12:
            continue
        point = np.linalg.solve(a, np.array([rows[i].b, rows[j].b], float))
        if any(r.a1 * point[0] + r.a2 * point[1] > r.b + FEAS_TOL for r in rows):
            continue
        # Three or more boundaries through one point is a degenerate vertex,
        # which several pairs would each report. Round to collapse them.
        # `+ 0.0` turns a -0.0 from the solve into 0.0, so no coordinate is
        # ever displayed as "-0".
        found[(round(point[0], 9), round(point[1], 9))] = (
            float(point[0]) + 0.0, float(point[1]) + 0.0,
        )

    vertices = sorted(found.values())
    active = [
        tuple(
            label
            for r, label in zip(rows, labels)
            if abs(r.a1 * v[0] + r.a2 * v[1] - r.b) <= FEAS_TOL
        )
        for v in vertices
    ]
    return vertices, active


def improving_ray(constraints: list[Row], c: tuple[float, float]) -> np.ndarray | None:
    """A feasible direction of unlimited improvement, if one exists.

    The region recedes along d when A d <= 0 for every row, the axis rows
    included, which is what forces d >= 0. In two variables such a cone can
    only have extreme rays along an axis or along some constraint boundary, so
    those are the only directions worth testing.
    """
    rows, _ = all_rows(constraints)
    candidates = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    for r in rows:
        d = np.array([-r.a2, r.a1], float)
        norm = np.linalg.norm(d)
        if norm > 1e-12:
            candidates.extend((d / norm, -d / norm))

    for d in candidates:
        if all(r.a1 * d[0] + r.a2 * d[1] <= 1e-9 for r in rows):
            if c[0] * d[0] + c[1] * d[1] > 1e-9:
                return d
    return None


def recedes(constraints: list[Row]) -> bool:
    """True when the feasible region itself runs off to infinity."""
    rows, _ = all_rows(constraints)
    candidates = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    for r in rows:
        d = np.array([-r.a2, r.a1], float)
        norm = np.linalg.norm(d)
        if norm > 1e-12:
            candidates.extend((d / norm, -d / norm))
    return any(
        all(r.a1 * d[0] + r.a2 * d[1] <= 1e-9 for r in rows) for d in candidates
    )


@dataclass(frozen=True)
class Solution:
    status: str  # "ok", "empty" or "unbounded"
    vertices: list[tuple[float, float]]
    values: list[float]
    active: list[tuple[str, ...]]
    optimal: list[int]  # indices into vertices; more than one means a tie
    tie_edges: list[tuple[int, int]]
    unbounded_region: bool

    @property
    def is_tie(self) -> bool:
        return len(self.optimal) > 1

    @property
    def best_value(self) -> float:
        return self.values[self.optimal[0]] if self.optimal else float("nan")


def solve(constraints: list[Row], c: tuple[float, float]) -> Solution:
    """Enumerate the region, score every vertex, and find the optimal set."""
    vertices, active = enumerate_vertices(constraints)

    # x1, x2 >= 0 makes the region pointed, so a non-empty region always has at
    # least one vertex. No vertices therefore means no feasible points at all.
    if not vertices:
        return Solution("empty", [], [], [], [], [], False)

    ray = improving_ray(constraints, c)
    if ray is not None:
        return Solution("unbounded", vertices, [], active, [], [], True)

    values = [c[0] * v[0] + c[1] * v[1] + 0.0 for v in vertices]
    best = max(values)
    tol = TIE_REL_TOL * max(1.0, abs(best))
    optimal = [i for i, v in enumerate(values) if best - v <= tol]

    # Two vertices of a plane polygon are joined by an edge exactly when they
    # share an active constraint, so a tie between adjacent vertices means the
    # whole edge between them is optimal.
    tie_edges = [
        (i, j)
        for i, j in combinations(optimal, 2)
        if set(active[i]) & set(active[j])
    ]

    return Solution("ok", vertices, values, active, optimal, tie_edges,
                    recedes(constraints))


def solver_check(
    constraints: list[Row], c: tuple[float, float], solution: Solution
) -> tuple[bool, str]:
    """Confirm the enumerated answer against SciPy HiGHS. Never resolve, report.

    linprog minimises, so the maximisation is passed as -c and the reported
    objective is negated back.
    """
    result = linprog(
        c=[-c[0], -c[1]],
        A_ub=[[r.a1, r.a2] for r in constraints] or None,
        b_ub=[r.b for r in constraints] or None,
        bounds=[(0, None), (0, None)],
        method="highs",
    )

    expected = {"ok": 0, "unbounded": 3, "empty": 2}[solution.status]
    if result.status != expected:
        return False, (
            f"The vertex enumeration reports '{solution.status}' but HiGHS "
            f"returns status {result.status} ({result.message.strip()})."
        )
    if solution.status != "ok":
        return True, ""

    solver_value = -float(result.fun)
    gap = abs(solver_value - solution.best_value)
    if gap > SOLVER_REL_TOL * max(1.0, abs(solver_value)):
        return False, (
            f"The vertex enumeration gives {solution.best_value:,.6g} and "
            f"HiGHS gives {solver_value:,.6g}. These should agree."
        )
    return True, ""


# --- Presets ---------------------------------------------------------------

DEFAULT_ROWS = [Row(1.0, 1.0, 12.0), Row(2.0, 1.0, 16.0)]

PRESETS: dict[str, dict] = {
    "Default (two constraints)": {
        "rows": DEFAULT_ROWS,
        "note": "The problem from the lecture. Two constraints, four vertices.",
    },
    "Adds a redundant constraint": {
        "rows": DEFAULT_ROWS + [Row(1.0, 0.0, 10.0)],
        "note": (
            "x₁ ≤ 10 is added. Nothing in the region ever reaches x₁ = 10, so "
            "the constraint never binds, the vertex set is unchanged and the "
            "answer is unchanged. Adding a constraint can change nothing at all."
        ),
    },
    "Adds a binding constraint": {
        "rows": DEFAULT_ROWS + [Row(0.0, 1.0, 6.0)],
        "note": (
            "x₂ ≤ 6 is added. It cuts the corner at (4, 8) off the region, so "
            "the old optimum is no longer feasible. The answer moves to a new "
            "vertex and the objective value falls."
        ),
    },
    "Producer problem (Topic 3)": {
        "rows": None,
        "note": "",
    },
}


# --- Plot ------------------------------------------------------------------

def _clip(a1: float, a2: float, b: float, xlim, ylim):
    """The segment of the line a1*x1 + a2*x2 = b that lies inside the axes."""
    norm = float(np.hypot(a1, a2))
    if norm < 1e-12:
        return None
    p0 = np.array([a1, a2], float) * b / norm**2
    d = np.array([-a2, a1], float) / norm

    t_lo, t_hi = -1e9, 1e9
    for axis, (lo, hi) in enumerate((xlim, ylim)):
        if abs(d[axis]) < 1e-12:
            if p0[axis] < lo - 1e-9 or p0[axis] > hi + 1e-9:
                return None
            continue
        t1 = (lo - p0[axis]) / d[axis]
        t2 = (hi - p0[axis]) / d[axis]
        t_lo = max(t_lo, min(t1, t2))
        t_hi = min(t_hi, max(t1, t2))

    if t_hi <= t_lo:
        return None
    return p0 + t_lo * d, p0 + t_hi * d


def axis_limits(vertices: list[tuple[float, float]]) -> tuple[tuple, tuple]:
    """Fixed axes, derived from the region only.

    The region does not depend on c, so these do not move while the slider
    moves. If they did, a student would read the jump as the picture rescaling
    rather than the answer changing.

    Both axes are then padded to a common span. The figure holds x and y to the
    same scale so that the gradient arrow really is perpendicular to the
    objective contours, and without this the square drawing area that forces
    would be squeezed into a narrow strip of the column, which is what makes
    tick labels unreadable over a shared screen.
    """
    xs = [v[0] for v in vertices] + [0.0]
    ys = [v[1] for v in vertices] + [0.0]
    x_lo, x_hi = -0.06 * max(max(xs), 1.0), 1.22 * max(max(xs), 1.0)
    y_lo, y_hi = -0.06 * max(max(ys), 1.0), 1.18 * max(max(ys), 1.0)
    span = max(x_hi - x_lo, y_hi - y_lo)
    return (x_lo, x_lo + span), (y_lo, y_lo + span)


def build_figure(
    constraints: list[Row], c: tuple[float, float], solution: Solution
) -> go.Figure:
    xlim, ylim = axis_limits(solution.vertices)
    fig = go.Figure()

    # Region fill. Vertices are ordered by angle about the centroid so the
    # polygon closes without crossing itself.
    pts = np.array(solution.vertices, float)
    centre = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - centre[1], pts[:, 0] - centre[0]))
    ring = pts[order]
    fig.add_trace(go.Scatter(
        x=list(ring[:, 0]) + [ring[0, 0]],
        y=list(ring[:, 1]) + [ring[0, 1]],
        fill="toself", fillcolor=LAVENDER,
        line=dict(color=LAVENDER, width=0),
        name="Feasible region", hoverinfo="skip",
    ))

    # Constraint boundaries.
    for row in constraints:
        clipped = _clip(row.a1, row.a2, row.b, xlim, ylim)
        if clipped is None:
            continue
        p, q = clipped
        fig.add_trace(go.Scatter(
            x=[p[0], q[0]], y=[p[1], q[1]],
            mode="lines", line=dict(color=NAVY, width=2.4),
            name=row_label(row), hoverinfo="skip",
        ))

    # Objective contours. The optimum's contour solid, three lower ones dashed,
    # which is what makes the family of parallel lines and its direction of
    # improvement visible at a glance.
    if np.hypot(c[0], c[1]) > 1e-12 and solution.status == "ok":
        best = solution.best_value
        levels = [(best, "solid", 3.0)]
        if abs(best) > 1e-9:
            levels += [(best * f, "dash", 1.6) for f in (0.75, 0.5, 0.25)]
        for n, (level, dash, width) in enumerate(levels):
            clipped = _clip(c[0], c[1], level, xlim, ylim)
            if clipped is None:
                continue
            p, q = clipped
            fig.add_trace(go.Scatter(
                x=[p[0], q[0]], y=[p[1], q[1]], mode="lines",
                line=dict(color=PURPLE, width=width, dash=dash),
                opacity=1.0 if n == 0 else 0.55,
                name=(f"Objective = {level:,.6g}" if n == 0
                      else "Lower objective values"),
                showlegend=n <= 1,
                hoverinfo="skip",
            ))

        # Gradient (c₁, c₂), anchored at the origin. The axes are held to equal
        # scale below, so this genuinely looks perpendicular to the contours.
        span = min(xlim[1] - xlim[0], ylim[1] - ylim[0])
        tip = np.array(c, float) / np.hypot(c[0], c[1]) * 0.30 * span
        fig.add_trace(go.Scatter(
            x=[0, tip[0]], y=[0, tip[1]], mode="lines",
            line=dict(color=BLUE, width=3),
            name=f"Gradient ({c[0]:g}, {c[1]:g})", hoverinfo="skip",
        ))
        fig.add_annotation(
            x=tip[0], y=tip[1], ax=0, ay=0,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.3,
            arrowwidth=3, arrowcolor=BLUE, text="",
        )

    # The optimal edge, drawn before the vertex markers so the markers sit on
    # top of it.
    for n, (i, j) in enumerate(solution.tie_edges):
        vi, vj = solution.vertices[i], solution.vertices[j]
        fig.add_trace(go.Scatter(
            x=[vi[0], vj[0]], y=[vi[1], vj[1]], mode="lines",
            line=dict(color=PURPLE, width=11),
            opacity=0.85, name="Optimal edge, every point ties",
            showlegend=n == 0, hoverinfo="skip",
        ))

    # Vertices.
    optimal = set(solution.optimal)
    for is_opt in (False, True):
        idx = [i for i in range(len(solution.vertices)) if (i in optimal) == is_opt]
        if not idx:
            continue
        fig.add_trace(go.Scatter(
            x=[solution.vertices[i][0] for i in idx],
            y=[solution.vertices[i][1] for i in idx],
            mode="markers+text",
            marker=dict(
                size=17 if is_opt else 11,
                color=PURPLE if is_opt else NAVY,
                line=dict(color=NAVY, width=2.5 if is_opt else 1),
                symbol="circle",
            ),
            text=[f"({solution.vertices[i][0]:.4g}, {solution.vertices[i][1]:.4g})"
                  for i in idx],
            # A label centred over a vertex sitting on the x₂ axis is half cut
            # off by the left edge of the plot, so those ones are pushed right.
            textposition=[
                "top right"
                if solution.vertices[i][0] <= xlim[0] + 0.06 * (xlim[1] - xlim[0])
                else "top center"
                for i in idx
            ],
            textfont=dict(size=13, color=NAVY),
            customdata=[[solution.values[i]] if solution.values else [float("nan")]
                        for i in idx],
            hovertemplate=(
                "x₁ = %{x:.4g}, x₂ = %{y:.4g}<br>"
                "Objective = %{customdata[0]:,.6g}<extra></extra>"
            ),
            name="Optimum" if is_opt else "Vertices",
        ))

    fig.update_layout(
        height=620,
        margin=dict(l=66, r=18, t=86, b=58),
        paper_bgcolor="white", plot_bgcolor=LIMESTONE,
        font=dict(size=14, color=NAVY),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.005, xanchor="left", x=0,
            font=dict(size=12.5), bgcolor="rgba(255,255,255,0.75)",
            itemwidth=30, tracegroupgap=0,
        ),
        hoverlabel=dict(font_size=14),
    )
    fig.update_xaxes(
        title=dict(text="x₁", font=dict(size=17)),
        range=list(xlim), tickfont=dict(size=14), constrain="domain",
        gridcolor=SILVER, zeroline=True, zerolinecolor=NAVY, zerolinewidth=1.5,
    )
    fig.update_yaxes(
        title=dict(text="x₂", font=dict(size=17)),
        range=list(ylim), tickfont=dict(size=14),
        gridcolor=SILVER, zeroline=True, zerolinecolor=NAVY, zerolinewidth=1.5,
        scaleanchor="x", scaleratio=1, constrain="domain",
    )
    return fig


def vertex_table(solution: Solution) -> pd.DataFrame:
    """Every vertex, best first, with a flag marking the optimal rows."""
    frame = pd.DataFrame({
        "x₁": [v[0] for v in solution.vertices],
        "x₂": [v[1] for v in solution.vertices],
        "Objective": solution.values,
        "Active constraints": [", ".join(a) for a in solution.active],
        "_optimal": [i in set(solution.optimal) for i in range(len(solution.vertices))],
    })
    return frame.sort_values(
        ["Objective", "x₁"], ascending=[False, True]
    ).reset_index(drop=True)


# --- Page ------------------------------------------------------------------

BANNER = (
    "Every point on this edge is optimal. The solver will report one of them "
    "and will not tell you the others exist."
)


def _banner(text: str, strong: bool) -> str:
    edge = PURPLE if strong else NAVY
    return (
        f'<div style="background:{LAVENDER};border-left:7px solid {edge};'
        f'border-radius:9px;padding:.85rem 1.1rem;margin:.35rem 0 .9rem;'
        f'color:{NAVY};font-size:1.02rem;line-height:1.45;">'
        f'{html.escape(text)}</div>'
    )


def render() -> None:
    st.title("LP Vertex Walk")
    st.markdown(
        "**Where the optimum of a linear program sits, and why it jumps "
        "rather than slides**"
    )

    preset_name = st.selectbox(
        "Problem", list(PRESETS), key="lpvw_preset",
        help="Each preset changes the constraints. The objective is yours to rotate.",
    )
    preset = PRESETS[preset_name]

    if preset["rows"] is None:
        st.warning(
            "Coefficients pending confirmation. This preset is a placeholder. "
            "The producer problem from Topic 3 has a verified optimum in the "
            "course notes and it is not reproduced here until those exact "
            "numbers are supplied, because a wrong version would contradict "
            "the recorded lecture. Choose another preset to continue."
        )
        return

    constraints: list[Row] = preset["rows"]

    st.caption(preset["note"])

    control_left, control_right = st.columns([3, 1])
    with control_left:
        c1 = float(st.slider(
            "c₁, the cost coefficient on x₁", 0, 100, 40, 1, key="lpvw_c1",
            help=(
                "Rotating the objective. The feasible region does not move as "
                "this changes, only the family of objective lines does."
            ),
        ))
    with control_right:
        c2 = float(st.number_input(
            "c₂", min_value=0.0, max_value=100.0, value=30.0, step=1.0,
            key="lpvw_c2",
        ))

    c = (c1, c2)
    st.markdown(
        f"Maximise **{c1:g} x₁ + {c2:g} x₂**  subject to  "
        + ",  ".join(row_label(r) for r in constraints)
        + ",  x₁ ≥ 0,  x₂ ≥ 0"
    )

    solution = solve(constraints, c)

    if solution.status == "empty":
        st.error(
            "There is no feasible region. No pair of values for x₁ and x₂ "
            "satisfies every constraint at once, so there is nothing to "
            "optimise. Relax one of the constraints."
        )
        return

    if solution.status == "unbounded":
        st.error(
            "The objective has no finite maximum. The feasible region runs "
            "off to infinity in a direction that keeps improving the "
            "objective, so no matter which point you name, a better one "
            "exists. Add a constraint that limits the region."
        )
        return

    agrees, disagreement = solver_check(constraints, c, solution)
    if not agrees:
        st.error(
            "The two independent calculations of this answer disagree, so no "
            "answer is shown. " + disagreement
        )
        return

    plot_col, panel_col = st.columns([3, 2])

    with plot_col:
        if solution.is_tie:
            st.markdown(_banner(BANNER, strong=True), unsafe_allow_html=True)
        st.plotly_chart(build_figure(constraints, c, solution),
                        width="stretch", key="lpvw_plot")
        if solution.unbounded_region:
            st.caption(
                "This region is unbounded. The shaded area shows the part "
                "near the origin. The objective still has a finite maximum "
                "at a vertex."
            )

    with panel_col:
        st.subheader("Current answer")
        winners = [solution.vertices[i] for i in solution.optimal]
        if solution.is_tie:
            listed = " and ".join(f"({v[0]:.4g}, {v[1]:.4g})" for v in winners)
            st.markdown(
                f"Objective **{solution.best_value:,.6g}**, achieved at every "
                f"point of the edge between {listed}. A solver reports one of "
                "them, chosen by its own pivoting rule."
            )
        else:
            x1, x2 = winners[0]
            metric_left, metric_right = st.columns(2)
            metric_left.metric("x₁*", f"{x1:,.4g}")
            metric_right.metric("x₂*", f"{x2:,.4g}")
            st.metric("Objective", f"{solution.best_value:,.6g}")

        # For a tie the honest answer is the constraint the whole optimal edge
        # lies on, which is the intersection, not the union, of the endpoints'
        # active sets.
        binding = sorted(set.intersection(
            *(set(solution.active[i]) for i in solution.optimal)
        ))
        st.markdown("**Binding constraints at the optimum**")
        st.markdown("\n".join(f"- {b}" for b in binding) or "- none")
        st.caption("Confirmed independently by SciPy HiGHS on this recompute.")

        st.subheader("Every vertex")
        frame = vertex_table(solution)
        flags = frame["_optimal"].tolist()
        styled = (
            frame.drop(columns="_optimal")
            .style
            .apply(
                lambda row: [f"background-color: {LAVENDER}; color: {NAVY}; "
                             "font-weight: 600"] * 4 if flags[row.name] else [""] * 4,
                axis=1,
            )
            .format({"x₁": "{:.4g}", "x₂": "{:.4g}", "Objective": "{:,.6g}"})
        )
        st.dataframe(styled, width="stretch", hide_index=True)
        st.caption(
            "Sorted best first. Check any row by hand: multiply the "
            "coordinates by c₁ and c₂ and add."
        )

    st.divider()
    st.markdown(
        """
**What to watch while c₁ moves**

1. The dashed purple lines are the objective, one line per value. Moving c₁
   rotates that whole family. It does not move the region, which is drawn from
   the constraints alone.
2. The optimum sits still, then jumps. It is never in the interior of the
   region, and it never slides gradually along an edge.
3. At the angle where it jumps, the highlighted edge is entirely optimal. Every
   point on it has the same objective value, which you can confirm in the
   vertex table where two rows carry the same number. That is the case a solver
   answers without warning you that it had a choice.
"""
    )
