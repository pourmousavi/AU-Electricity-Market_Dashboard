"""The duality page must say WHAT problem it is showing, and mean it.

Three things this pins, all of them student-visible:

1. A no-solution message names WHY. Live 1 drives the primal unbounded
   (Minimise, c1 < 0), where "No feasible solution found" is the wrong word.
2. The worked-example picker actually rewrites the sliders. It used to set a
   message and nothing else, so every example rendered the same problem.
3. strong_duality and weak_duality render DIFFERENT things. They share one
   _kit page, so it is easy for them to collapse back into the same page.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from experiments import strong_duality, weak_duality
from experiments._kit.duality import CUSTOM, _no_solution_message

ROOT = Path(__file__).resolve().parent.parent


def _harness(exp_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        f"from experiments import {exp_id}\n"
        f"{exp_id}.render()\n"
    )


def _run(exp_id: str) -> AppTest:
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    assert not app.exception, "; ".join(e.message for e in app.exception)
    return app


def _text(app: AppTest) -> str:
    parts = []
    for kind in ("markdown", "info", "warning", "error", "success", "subheader"):
        parts.extend(str(e.value) for e in getattr(app, kind))
    return "\n".join(parts)


# --- 1. the message names the status ---------------------------------------

def test_message_names_the_status() -> None:
    assert "Infeasible" in _no_solution_message(2)
    assert "Unbounded" in _no_solution_message(3)
    assert _no_solution_message(None) == "No feasible solution found"


def test_unbounded_primal_says_unbounded() -> None:
    app = _run("strong_duality")
    app.selectbox(key="dual_type").set_value("Minimize").run()
    app.slider(key="dual_c1").set_value(-1.0).run()

    written = _text(app)
    assert "Unbounded" in written, "primal should report unbounded"
    assert "Infeasible" in written, "its dual should report infeasible"


# --- 2. the picker drives the problem --------------------------------------

def test_preset_rewrites_the_sliders() -> None:
    """The complaint this fixes: picking an example changed nothing above it."""
    app = _run("weak_duality")
    assert app.session_state["dual_c1"] == 3.0
    assert app.session_state["dual_type"] == "Maximize"

    app.selectbox(key="dual_preset").set_value(weak_duality.duality.UNBOUNDED_NAME).run()

    assert app.session_state["dual_c1"] == -1.0
    assert app.session_state["dual_type"] == "Minimize"
    assert app.slider(key="dual_c1").value == -1.0, "the slider itself must move"


@pytest.mark.parametrize("preset_name, expected", [
    ("UNBOUNDED_NAME", "Unbounded"),
    ("INFEASIBLE_NAME", "Infeasible"),
])
def test_each_failure_preset_produces_the_case_it_names(preset_name, expected) -> None:
    app = _run("weak_duality")
    name = getattr(weak_duality.duality, preset_name)
    app.selectbox(key="dual_preset").set_value(name).run()
    assert expected in _text(app), f"{name} should render {expected!r}"


def test_moving_a_slider_returns_the_picker_to_custom() -> None:
    """A picker still naming an example the sliders no longer match is a lie."""
    app = _run("weak_duality")
    app.selectbox(key="dual_preset").set_value(weak_duality.duality.UNBOUNDED_NAME).run()
    assert app.session_state["dual_preset"] != CUSTOM

    app.slider(key="dual_d1").set_value(7.0).run()
    assert app.session_state["dual_preset"] == CUSTOM


def test_infeasible_preset_needs_the_widened_slider_range() -> None:
    """It sets a2 = -1: with the old [0.1, 5.0] range this was unreachable."""
    assert strong_duality.duality.INFEASIBLE_PRIMAL["dual_a2"] < 0
    app = _run("weak_duality")
    assert app.slider(key="dual_a2").min < 0


# --- 3. the two experiments differ -----------------------------------------

def test_strong_and_weak_render_different_pages() -> None:
    strong, weak = _text(_run("strong_duality")), _text(_run("weak_duality"))
    assert "Complementary Slackness" in strong
    assert "Complementary Slackness" not in weak
    assert "sandwich" in weak
    assert "sandwich" not in strong


def test_strong_duality_shows_every_product_zero() -> None:
    """The mechanism behind gap = 0, not a restatement of it."""
    app = _run("strong_duality")
    assert "Every product is zero" in _text(app)


def test_weak_duality_opens_on_a_visible_gap() -> None:
    """Seeded picks are feasible but NOT optimal, or the panel shows 0.000."""
    app = _run("weak_duality")
    written = _text(app)
    assert "gap **15.000**" in written, (
        "expected c'x = 5 against d'l = 20 for the seeded pair; got:\n" + written
    )


def test_weak_duality_rejects_an_infeasible_pick() -> None:
    app = _run("weak_duality")
    app.number_input(key="weak_x1").set_value(50.0).run()

    written = _text(app)
    assert "not feasible" in written
    assert "gap **" not in written, "no sandwich should be drawn for an infeasible x"


def test_weak_duality_gap_closes_at_the_optimum() -> None:
    """The one pair where the inequality is tight is the optimum itself."""
    app = _run("weak_duality")
    for key, value in (("weak_x1", 2.0), ("weak_x2", 2.0),
                       ("weak_l1", 1.0), ("weak_l2", 1.0)):
        app.number_input(key=key).set_value(value).run()

    assert "both picks are optimal" in _text(app)


def test_slack_preset_produces_the_zero_shadow_price_it_claims() -> None:
    """Its note says row 2 is slack with a zero price — check the page agrees."""
    app = _run("strong_duality")
    app.selectbox(key="dual_preset").set_value(
        strong_duality.duality.SLACK_NAME).run()

    assert "Constraint 2 is **not binding**" in _text(app)

    # The slackness table is a dataframe, so it is not in _text(): read it.
    table = app.dataframe[0].value
    assert float(table["Its multiplier"][1]) == 0.0, "row 2's price should be zero"
    assert float(table["Slack"][1]) > 0.0, "row 2 should have slack"
    assert all(abs(float(v)) < 1e-6 for v in table["Product"])


def test_every_shipped_example_fits_its_sliders() -> None:
    """A preset outside a slider's range raises and takes the whole page down.

    This is how ONE_ROW_SLACK shipped d2 = 20 against a slider capped at 10.
    """
    from experiments import duality_theorems
    from experiments._kit.duality import RANGES

    everything = {}
    for module in (strong_duality, weak_duality, duality_theorems):
        everything[f"{module.__name__} defaults"] = module.DEFAULTS
        for label, values in module.PRESETS.items():
            everything[f"{module.__name__}: {label}"] = values

    for label, values in everything.items():
        for key, value in values.items():
            if key not in RANGES:      # dual_type is the sense, not a slider
                continue
            low, high = RANGES[key]
            assert low <= value <= high, (
                f"{label} sets {key}={value}, outside the slider's [{low}, {high}]"
            )
