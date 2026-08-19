"""The numbers this experiment shows students must be exactly these numbers.

The lecturer tells the room the tool is the source of truth, so the default
problem's vertices, its optimum, and the two rotation angles at which an entire
edge becomes optimal are all pinned here. The tie test in particular asserts
BOTH directions: ties at c1 = 30 and c1 = 60, and at no other integer the
slider can reach. A tie detector that fired anywhere else would put the
multiple-optima banner in front of students at a point where the optimum is in
fact unique.
"""
import numpy as np
import pytest

from experiments.lp_vertex_walk import (
    DEFAULT_ROWS,
    PRESETS,
    Row,
    axis_limits,
    enumerate_vertices,
    improving_ray,
    row_label,
    solve,
    solver_check,
    vertex_table,
)

C2 = 30.0
SLIDER = range(0, 101)  # the c1 slider, 0 to 100 in steps of 1


def _vertex_set(vertices):
    return {(round(x, 9), round(y, 9)) for x, y in vertices}


# --- The default problem ---------------------------------------------------

def test_default_problem_has_exactly_four_vertices() -> None:
    vertices, _ = enumerate_vertices(DEFAULT_ROWS)
    assert _vertex_set(vertices) == {(0.0, 0.0), (8.0, 0.0), (4.0, 8.0), (0.0, 12.0)}


def test_default_problem_vertex_values() -> None:
    solution = solve(DEFAULT_ROWS, (40.0, C2))
    values = {
        (round(x, 9), round(y, 9)): v
        for (x, y), v in zip(solution.vertices, solution.values)
    }
    assert values == {
        (0.0, 0.0): 0.0,
        (8.0, 0.0): 320.0,
        (4.0, 8.0): 400.0,
        (0.0, 12.0): 360.0,
    }


def test_default_optimum_is_400_at_4_8() -> None:
    solution = solve(DEFAULT_ROWS, (40.0, C2))
    assert solution.status == "ok"
    assert not solution.is_tie
    assert solution.vertices[solution.optimal[0]] == (4.0, 8.0)
    assert solution.best_value == pytest.approx(400.0)


def test_optimum_is_where_the_two_structural_constraints_meet() -> None:
    solution = solve(DEFAULT_ROWS, (40.0, C2))
    active = solution.active[solution.optimal[0]]
    assert set(active) == {"x₁ + x₂ ≤ 12", "2x₁ + x₂ ≤ 16"}


# --- The rotation walk -----------------------------------------------------

EXPECTED_WALK = [
    (0, (0.0, 12.0)), (1, (0.0, 12.0)), (29, (0.0, 12.0)),
    (31, (4.0, 8.0)), (40, (4.0, 8.0)), (59, (4.0, 8.0)),
    (61, (8.0, 0.0)), (80, (8.0, 0.0)), (100, (8.0, 0.0)),
]


@pytest.mark.parametrize("c1,expected", EXPECTED_WALK)
def test_optimal_vertex_walks_the_expected_path(c1: int, expected) -> None:
    solution = solve(DEFAULT_ROWS, (float(c1), C2))
    assert not solution.is_tie
    assert solution.vertices[solution.optimal[0]] == expected


def test_ties_occur_at_30_and_60_and_nowhere_else() -> None:
    tied = [c1 for c1 in SLIDER if solve(DEFAULT_ROWS, (float(c1), C2)).is_tie]
    assert tied == [30, 60]


def test_tie_at_30_is_the_edge_from_0_12_to_4_8() -> None:
    solution = solve(DEFAULT_ROWS, (30.0, C2))
    tied = {solution.vertices[i] for i in solution.optimal}
    assert tied == {(0.0, 12.0), (4.0, 8.0)}
    assert len(solution.tie_edges) == 1
    assert solution.best_value == pytest.approx(360.0)


def test_tie_at_60_is_the_edge_from_4_8_to_8_0() -> None:
    solution = solve(DEFAULT_ROWS, (60.0, C2))
    tied = {solution.vertices[i] for i in solution.optimal}
    assert tied == {(4.0, 8.0), (8.0, 0.0)}
    assert len(solution.tie_edges) == 1
    assert solution.best_value == pytest.approx(480.0)


def test_a_tie_is_a_genuine_edge_not_two_loose_vertices() -> None:
    """The two tied vertices must share a constraint, or there is no edge."""
    for c1 in (30.0, 60.0):
        solution = solve(DEFAULT_ROWS, (c1, C2))
        i, j = solution.tie_edges[0]
        assert set(solution.active[i]) & set(solution.active[j])


def test_every_point_on_the_tied_edge_really_does_score_the_same() -> None:
    """The claim in the banner, checked at points between the two vertices."""
    for c1 in (30.0, 60.0):
        solution = solve(DEFAULT_ROWS, (c1, C2))
        i, j = solution.tie_edges[0]
        a = np.array(solution.vertices[i])
        b = np.array(solution.vertices[j])
        for t in (0.0, 0.1, 0.37, 0.5, 0.83, 1.0):
            point = a + t * (b - a)
            assert c1 * point[0] + C2 * point[1] == pytest.approx(
                solution.best_value
            )


def test_ties_are_not_detected_by_hard_coded_angles() -> None:
    """Tilt the constraints and both tie angles must move with them.

    A tie happens when the objective family becomes parallel to an edge, so the
    tie angle is set by the SLOPE of a constraint, not by its right-hand side.
    Tilting both structural constraints therefore has to move both tie points.
    If 30 and 60 were baked in, this fails, which is the whole reason ties are
    detected by comparing objective values instead.
    """
    tilted = [Row(1.0, 2.0, 24.0), Row(3.0, 1.0, 18.0)]
    tied = [c1 for c1 in SLIDER if solve(tilted, (float(c1), C2)).is_tie]
    assert tied == [15, 90]


def test_moving_a_right_hand_side_alone_leaves_the_tie_angles_alone() -> None:
    """The other half of the same point, and the easier one to get wrong.

    Changing b resizes the region and moves the vertices, but every edge keeps
    its slope, so the angles at which an edge ties are unchanged. A student who
    expects the tie to follow the vertex needs this to be true.
    """
    resized = [DEFAULT_ROWS[0], Row(2.0, 1.0, 20.0)]
    assert solve(resized, (40.0, C2)).vertices != solve(DEFAULT_ROWS, (40.0, C2)).vertices
    tied = [c1 for c1 in SLIDER if solve(resized, (float(c1), C2)).is_tie]
    assert tied == [30, 60]


# --- Independent confirmation ----------------------------------------------

@pytest.mark.parametrize("c1", list(SLIDER))
def test_enumeration_agrees_with_highs_at_every_slider_position(c1: int) -> None:
    c = (float(c1), C2)
    solution = solve(DEFAULT_ROWS, c)
    agrees, message = solver_check(DEFAULT_ROWS, c, solution)
    assert agrees, message


# --- Presets ---------------------------------------------------------------

def test_redundant_constraint_changes_nothing() -> None:
    plain = solve(DEFAULT_ROWS, (40.0, C2))
    padded = solve(PRESETS["Adds a redundant constraint"]["rows"], (40.0, C2))
    assert _vertex_set(padded.vertices) == _vertex_set(plain.vertices)
    assert padded.best_value == pytest.approx(plain.best_value)
    assert padded.best_value == pytest.approx(400.0)


def test_binding_constraint_moves_the_optimum_and_lowers_the_value() -> None:
    cut = solve(PRESETS["Adds a binding constraint"]["rows"], (40.0, C2))
    assert _vertex_set(cut.vertices) == {(0.0, 0.0), (8.0, 0.0), (5.0, 6.0), (0.0, 6.0)}
    assert cut.vertices[cut.optimal[0]] == (5.0, 6.0)
    assert cut.best_value == pytest.approx(380.0)
    assert cut.best_value < 400.0


def test_producer_preset_ships_no_coefficients() -> None:
    """It must stay a placeholder until the verified numbers arrive."""
    assert PRESETS["Producer problem (Topic 3)"]["rows"] is None


# --- Degenerate regions ----------------------------------------------------

def test_empty_region_is_reported_not_crashed() -> None:
    # x1 + x2 <= 12 together with x1 + x2 >= 20.
    solution = solve([Row(1.0, 1.0, 12.0), Row(-1.0, -1.0, -20.0)], (40.0, C2))
    assert solution.status == "empty"
    assert solution.vertices == []


def test_unbounded_objective_is_reported_not_crashed() -> None:
    solution = solve([], (40.0, C2))
    assert solution.status == "unbounded"
    assert improving_ray([], (40.0, C2)) is not None


def test_unbounded_region_with_a_finite_optimum_still_solves() -> None:
    """x2 <= 6 alone: the region runs off along x1, but c = (0, 30) does not."""
    solution = solve([Row(0.0, 1.0, 6.0)], (0.0, C2))
    assert solution.status == "ok"
    assert solution.unbounded_region
    assert solution.best_value == pytest.approx(180.0)


def test_highs_agrees_on_the_degenerate_cases() -> None:
    empty = [Row(1.0, 1.0, 12.0), Row(-1.0, -1.0, -20.0)]
    assert solver_check(empty, (40.0, C2), solve(empty, (40.0, C2)))[0]
    assert solver_check([], (40.0, C2), solve([], (40.0, C2)))[0]


# --- Presentation ----------------------------------------------------------

def test_axes_do_not_move_while_the_slider_moves() -> None:
    """The region does not depend on c, so neither may the axis limits."""
    limits = {axis_limits(solve(DEFAULT_ROWS, (float(c1), C2)).vertices)
              for c1 in SLIDER}
    assert len(limits) == 1


def test_vertex_table_is_sorted_best_first_with_the_optimum_flagged() -> None:
    frame = vertex_table(solve(DEFAULT_ROWS, (40.0, C2)))
    assert list(frame["Objective"]) == [400.0, 360.0, 320.0, 0.0]
    assert frame["_optimal"].tolist() == [True, False, False, False]


def test_both_tied_rows_are_flagged_in_the_table() -> None:
    frame = vertex_table(solve(DEFAULT_ROWS, (30.0, C2)))
    assert frame["_optimal"].tolist().count(True) == 2


def test_constraint_labels_read_the_way_they_are_written_on_the_board() -> None:
    assert row_label(Row(1.0, 1.0, 12.0)) == "x₁ + x₂ ≤ 12"
    assert row_label(Row(2.0, 1.0, 16.0)) == "2x₁ + x₂ ≤ 16"
    assert row_label(Row(1.0, 0.0, 10.0)) == "x₁ ≤ 10"
    assert row_label(Row(0.0, 1.0, 6.0)) == "x₂ ≤ 6"


def test_no_coordinate_is_ever_shown_as_negative_zero() -> None:
    solution = solve(DEFAULT_ROWS, (40.0, C2))
    shown = [f"{n:.4g}" for v in solution.vertices for n in v]
    shown += [f"{v:,.6g}" for v in solution.values]
    assert not [s for s in shown if s.startswith("-0")]


def test_interface_strings_use_australian_english_and_no_em_dashes() -> None:
    from pathlib import Path
    source = Path(__file__).resolve().parent.parent / "experiments" / "lp_vertex_walk.py"
    text = source.read_text(encoding="utf-8")
    assert "—" not in text
    # `scipy.optimize` is a package name, not an interface string. Anything
    # else spelling it with a z is one of ours and is wrong.
    prose = "\n".join(l for l in text.splitlines() if "scipy.optimize" not in l)
    assert "optimize" not in prose.lower()


# --- The page itself -------------------------------------------------------
#
# Everything above tests the model. This tests the wiring: that moving the
# slider to a tie actually puts the multiple-optima banner in front of the
# room, and that it is absent otherwise. A correct tie detector wired to
# nothing would pass every test above.

HARNESS = """
import sys
sys.path.insert(0, {root!r})
import experiments.lp_vertex_walk as module
module.render()
"""


def _page():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    root = str(Path(__file__).resolve().parent.parent)
    return AppTest.from_string(HARNESS.format(root=root), default_timeout=180).run()


def test_the_banner_appears_at_a_tie_and_only_at_a_tie() -> None:
    from experiments.lp_vertex_walk import BANNER

    app = _page()
    assert not app.exception, [e.message for e in app.exception]

    def banner_showing() -> bool:
        return any(BANNER in m.value for m in app.markdown)

    assert not banner_showing(), "c₁ = 40 has a unique optimum"
    for c1 in (30, 60):
        app.slider[0].set_value(c1).run()
        assert not app.exception, [e.message for e in app.exception]
        assert banner_showing(), f"no multiple-optima banner at c₁ = {c1}"
    app.slider[0].set_value(45).run()
    assert not banner_showing(), "c₁ = 45 has a unique optimum"


def test_the_producer_placeholder_shows_no_problem_at_all() -> None:
    """It must not quietly present some other producer problem as the real one."""
    app = _page()
    app.selectbox[0].set_value("Producer problem (Topic 3)").run()
    assert not app.exception, [e.message for e in app.exception]
    assert any("pending confirmation" in w.value for w in app.warning)
    assert len(app.dataframe) == 0
