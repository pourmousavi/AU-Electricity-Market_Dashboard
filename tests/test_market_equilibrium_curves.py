"""The demand curve must be drawn as a step function, like every other stack.

The bug this pins: the demand curve's tail was appended as a single far-right
point at price 0, so the last segment ran diagonally from the final bid's price
down to the axis instead of dropping vertically and then running flat. It was
the one segment in the plot that did not look like a step.
"""
from experiments.market_equilibrium import create_market_equilibrium_plot

SUPPLY = [
    {"price": 20.0, "quantity": 10.0, "cumulative_quantity": 10.0},
    {"price": 40.0, "quantity": 10.0, "cumulative_quantity": 20.0},
]
DEMAND = [
    {"price": 90.0, "quantity": 8.0, "cumulative_quantity": 8.0},
    {"price": 30.0, "quantity": 7.0, "cumulative_quantity": 15.0},
]


def _trace(fig, name):
    return next(t for t in fig.data if t.name == name)


def test_demand_curve_ends_with_a_vertical_drop_then_a_flat_run() -> None:
    demand = _trace(create_market_equilibrium_plot(SUPPLY, DEMAND, []), "Demand Curve")
    xs, ys = list(demand.x), list(demand.y)

    # ...(last_qty, last_price), (last_qty, 0), (far_right, 0)
    last_qty = DEMAND[-1]["cumulative_quantity"]
    assert (xs[-3], ys[-3]) == (last_qty, DEMAND[-1]["price"])
    assert (xs[-2], ys[-2]) == (last_qty, 0), "no vertical drop at the last bid"
    assert ys[-1] == 0 and xs[-1] > last_qty, "no flat run after the drop"


def test_no_segment_of_the_demand_curve_is_diagonal() -> None:
    """Every segment is either horizontal or vertical — that is what a step is."""
    demand = _trace(create_market_equilibrium_plot(SUPPLY, DEMAND, []), "Demand Curve")
    xs, ys = list(demand.x), list(demand.y)

    diagonals = [
        ((xs[i], ys[i]), (xs[i + 1], ys[i + 1]))
        for i in range(len(xs) - 1)
        if xs[i] != xs[i + 1] and ys[i] != ys[i + 1]
    ]
    assert not diagonals, f"diagonal segment(s) in the demand curve: {diagonals}"
