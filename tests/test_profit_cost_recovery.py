"""The economics behind Profit & Fixed Cost Recovery.

Every figure here is hand-checked against the worked example in
docs/superpowers/specs/2026-08-13-profit-cost-recovery-economics-design.md.
"""
import pandas as pd
import pytest

from experiments.profit_cost_recovery import (
    _price_bands,
    achieved_return,
    annual_fixed_cost,
    capital_recovery_factor,
    dispatch,
    investment_metrics,
    marginal_cost,
)

BANDS = [
    {"price": 45.0, "hours": 4000.0},
    {"price": 85.0, "hours": 3500.0},
    {"price": 220.0, "hours": 1160.0},
    {"price": 800.0, "hours": 100.0},
]

# The spec's worked example, as keyword arguments.
EXAMPLE = dict(
    capacity_mw=400.0, life_years=25, capex_per_kw=900.0, wacc=0.07,
    fom_per_kw=25.0, fuel_price=9.5, efficiency_pct=33.0, vom=4.0,
    forced_outage_rate=0.08, planned_days=0.0, bands=BANDS,
)


def test_capital_recovery_factor_matches_the_hand_checked_value() -> None:
    assert capital_recovery_factor(0.07, 25) == pytest.approx(0.08581, abs=5e-6)


def test_capital_recovery_factor_at_zero_rate_is_straight_line() -> None:
    """No discounting means paying back 1/n of the capital each year."""
    assert capital_recovery_factor(0.0, 25) == pytest.approx(0.04)


def test_marginal_cost_is_fuel_over_efficiency_plus_vom() -> None:
    # 3.6 GJ per MWh at 100% efficiency -> 10.909 GJ/MWh at 33%.
    assert marginal_cost(9.5, 33.0, 4.0) == pytest.approx(107.6, abs=0.1)


def test_annual_fixed_cost_separates_capex_from_fixed_om() -> None:
    fixed = annual_fixed_cost(900.0, 400.0, 0.07, 25, 25.0)
    assert fixed["capex_total"] == pytest.approx(360_000_000)
    assert fixed["annualised_capex"] == pytest.approx(30_890_000, rel=1e-3)
    assert fixed["fixed_om"] == pytest.approx(10_000_000)
    assert fixed["total"] == pytest.approx(40_890_000, rel=1e-3)


def test_forced_outages_scale_every_band_equally() -> None:
    result = dispatch(BANDS, marginal_cost_value=0.0,
                      forced_outage_rate=0.08, planned_days=0.0)
    for band, original in zip(result, BANDS):
        assert band["available_hours"] == pytest.approx(original["hours"] * 0.92)


def test_planned_maintenance_comes_out_of_the_cheapest_hours_first() -> None:
    """21 days = 504 h, and the cheapest band has 3680 h available."""
    result = dispatch(BANDS, marginal_cost_value=0.0,
                      forced_outage_rate=0.08, planned_days=21.0)
    assert result[0]["available_hours"] == pytest.approx(4000 * 0.92 - 504)
    for band, original in zip(result[1:], BANDS[1:]):
        assert band["available_hours"] == pytest.approx(original["hours"] * 0.92)


def test_planned_maintenance_spills_into_the_next_cheapest_band() -> None:
    """200 days = 4800 h, more than the cheapest band's 3680 available."""
    result = dispatch(BANDS, marginal_cost_value=0.0,
                      forced_outage_rate=0.08, planned_days=200.0)
    assert result[0]["available_hours"] == pytest.approx(0.0)
    assert result[1]["available_hours"] == pytest.approx(3500 * 0.92 - (4800 - 3680))


def test_price_bands_coerces_a_nan_price_to_zero() -> None:
    """A cleared Price cell in st.data_editor becomes NaN; it must read as 0."""
    edited = pd.DataFrame([
        {"Band": "Off-peak", "Price ($/MWh)": float("nan"), "Hours/year": 4000.0},
        {"Band": "Peak", "Price ($/MWh)": 220.0, "Hours/year": 1160.0},
    ])
    assert _price_bands(edited) == [
        {"price": 0.0, "hours": 4000.0},
        {"price": 220.0, "hours": 1160.0},
    ]


def test_price_bands_coerces_a_nan_hours_to_zero() -> None:
    """A cleared Hours cell in st.data_editor becomes NaN; it must read as 0."""
    edited = pd.DataFrame([
        {"Band": "Off-peak", "Price ($/MWh)": 45.0, "Hours/year": float("nan")},
        {"Band": "Peak", "Price ($/MWh)": 220.0, "Hours/year": 1160.0},
    ])
    assert _price_bands(edited) == [
        {"price": 45.0, "hours": 0.0},
        {"price": 220.0, "hours": 1160.0},
    ]


def test_a_plant_runs_only_where_price_exceeds_its_marginal_cost() -> None:
    result = dispatch(BANDS, marginal_cost_value=107.6,
                      forced_outage_rate=0.08, planned_days=0.0)
    assert [band["running_hours"] for band in result[:2]] == [0.0, 0.0]
    assert result[2]["running_hours"] == pytest.approx(1160 * 0.92)
    assert result[3]["running_hours"] == pytest.approx(100 * 0.92)


def test_achieved_return_round_trips_through_the_recovery_factor() -> None:
    rate = achieved_return(360_000_000, 63_400_000, 25)
    assert capital_recovery_factor(rate, 25) * 360_000_000 == pytest.approx(
        63_400_000, rel=1e-6
    )


def test_achieved_return_is_none_when_capital_is_never_recovered() -> None:
    """$1M a year for 25 years does not repay $360M, at any discount rate."""
    assert achieved_return(360_000_000, 1_000_000, 25) is None


def test_achieved_return_is_none_for_a_non_finite_cash_flow() -> None:
    """A NaN or infinite cash flow must never reach bisection.

    Bisection with a NaN comparison leaves every guard False, `high` halves
    toward 0, and `capital_recovery_factor` then divides by zero -- this is
    the defence-in-depth guard against that, independent of what any caller
    upstream (e.g. `_price_bands`) already coerced.
    """
    assert achieved_return(360_000_000, float("nan"), 25) is None
    assert achieved_return(360_000_000, float("inf"), 25) is None


def test_achieved_return_is_none_for_a_non_finite_capex() -> None:
    assert achieved_return(float("nan"), 60_000_000, 25) is None
    assert achieved_return(float("inf"), 60_000_000, 25) is None


def test_the_worked_example_end_to_end() -> None:
    m = investment_metrics(**EXAMPLE)
    assert m["marginal_cost"] == pytest.approx(107.6, abs=0.1)
    assert m["fixed"]["total"] == pytest.approx(40_890_000, rel=1e-3)
    assert m["running_hours"] == pytest.approx(1159.2, abs=0.5)
    assert m["revenue"] == pytest.approx(123_400_000, rel=1e-3)
    assert m["variable_cost"] == pytest.approx(49_900_000, rel=1e-2)
    assert m["short_run_profit"] == pytest.approx(73_400_000, rel=1e-2)
    assert m["long_run_profit"] == pytest.approx(32_600_000, rel=1e-2)
    assert m["capacity_factor"] == pytest.approx(13.2, abs=0.1)
    assert m["achieved_return"] == pytest.approx(0.173, abs=0.002)
    assert m["is_viable"] is True


def test_the_scarcity_band_carries_most_of_the_profit() -> None:
    """The teaching point: 92 hours a year supply 78% of the long-run profit.

    Checked by hand: with the scarcity band the plant clears $32.55M, without
    it $7.07M. It stays viable either way -- the lesson is the concentration,
    not a sign flip.
    """
    with_scarcity = investment_metrics(**EXAMPLE)["long_run_profit"]
    without = investment_metrics(**dict(EXAMPLE, bands=BANDS[:3]))["long_run_profit"]
    assert without == pytest.approx(7_070_000, rel=1e-2)
    assert (with_scarcity - without) / with_scarcity == pytest.approx(0.783, abs=0.01)


def test_a_plant_priced_out_of_every_band_earns_nothing() -> None:
    m = investment_metrics(**dict(EXAMPLE, fuel_price=100.0))
    assert m["running_hours"] == 0.0
    assert m["revenue"] == 0.0
    assert m["short_run_profit"] == 0.0
    assert m["long_run_profit"] == pytest.approx(-m["fixed"]["total"])
    assert m["achieved_return"] is None
    assert m["is_viable"] is False


def test_a_fully_available_plant_runs_every_in_merit_hour() -> None:
    m = investment_metrics(**dict(EXAMPLE, forced_outage_rate=0.0))
    assert m["running_hours"] == pytest.approx(1260.0)


def test_the_waterfall_adds_up_to_long_run_profit() -> None:
    """A waterfall that does not close is worse than no waterfall."""
    from experiments.profit_cost_recovery import create_waterfall_plot

    m = investment_metrics(**EXAMPLE)
    steps = create_waterfall_plot(m).data[0].y
    revenue, less_variable, _, less_capex, less_fom, _ = steps
    assert revenue + less_variable + less_capex + less_fom == pytest.approx(
        m["long_run_profit"] / 1e6
    )


def test_the_waterfall_pins_each_label_to_its_own_value() -> None:
    """Closing to the right total is not enough -- swapping two bars (or their
    labels) still closes. Pin each bar's value and text to its own label so
    that mutation is caught too.
    """
    from experiments.profit_cost_recovery import create_waterfall_plot

    m = investment_metrics(**EXAMPLE)
    fixed = m["fixed"]
    trace = create_waterfall_plot(m).data[0]
    labels = list(trace.x)
    values = list(trace.y)
    text = list(trace.text)

    expected_values = {
        "Revenue": m["revenue"] / 1e6,
        "Variable cost": -m["variable_cost"] / 1e6,
        "Annualised CAPEX": -fixed["annualised_capex"] / 1e6,
        "Fixed O&M": -fixed["fixed_om"] / 1e6,
    }
    for label, value in expected_values.items():
        assert values[labels.index(label)] == pytest.approx(value)

    expected_text = {
        "Revenue": f"${m['revenue']/1e6:,.1f}M",
        "Variable cost": f"−${m['variable_cost']/1e6:,.1f}M",
        "Annualised CAPEX": f"−${fixed['annualised_capex']/1e6:,.1f}M",
        "Fixed O&M": f"−${fixed['fixed_om']/1e6:,.1f}M",
    }
    for label, expected in expected_text.items():
        assert text[labels.index(label)] == expected


def test_price_duration_plot_shades_running_hours_not_total_hours() -> None:
    """The shaded block is the hours the plant runs, not the hours in the band.

    Shading `band["hours"]` instead of `band["running_hours"]` would overstate
    a plant's running hours by the forced-outage rate -- exactly what this
    chart exists to show correctly.
    """
    from experiments.profit_cost_recovery import create_price_duration_plot

    m = investment_metrics(**EXAMPLE)
    fig = create_price_duration_plot(m)

    shaded = [trace for trace in fig.data if trace.fill == "toself"]
    in_merit = [b for b in m["dispatched"] if b["running_hours"] > 0]
    out_of_merit = [b for b in m["dispatched"] if b["running_hours"] == 0]

    # Sanity check that the worked example actually exercises both cases.
    assert in_merit and out_of_merit

    # Out-of-merit bands must not produce a shaded trace at all.
    assert len(shaded) == len(in_merit)

    # Shaded traces are added dearest-first, same order as `ordered` inside
    # the plot function.
    ordered_in_merit = sorted(in_merit, key=lambda band: -band["price"])
    for trace, band in zip(shaded, ordered_in_merit):
        width = trace.x[1] - trace.x[0]
        assert width == pytest.approx(band["running_hours"])



# --- Plant size: scale economies and the market's appetite -----------------
#
# Two effects pull in opposite directions as a plant gets bigger, and together
# they give plant size an optimum, which a flat $/kW model cannot express:
#
#   * CAPEX per kW falls with size (the scale exponent), pushing returns up;
#   * the market can only absorb so much output in any hour, so beyond that
#     limit the extra megawatts sit idle in every band while still being paid
#     for, pulling returns down.

from experiments.profit_cost_recovery import (  # noqa: E402
    REFERENCE_CAPACITY_MW,
    scaled_capex_per_kw,
)


def test_a_unit_exponent_means_no_scale_effect() -> None:
    """Exponent 1.0 must reproduce today's flat $/kW at any size."""
    for mw in (100.0, 400.0, 1500.0):
        assert scaled_capex_per_kw(900.0, mw, 1.0) == pytest.approx(900.0)


def test_at_the_reference_size_any_exponent_is_a_no_op() -> None:
    for exponent in (0.6, 0.85, 1.0):
        assert scaled_capex_per_kw(900.0, REFERENCE_CAPACITY_MW, exponent) == (
            pytest.approx(900.0)
        )


def test_bigger_plants_cost_less_per_kw() -> None:
    """Hand-checked: 900 x (mw/400)^(0.85-1)."""
    assert scaled_capex_per_kw(900.0, 200.0, 0.85) == pytest.approx(999.0, abs=1.0)
    assert scaled_capex_per_kw(900.0, 1000.0, 0.85) == pytest.approx(784.0, abs=1.0)


def test_scale_economies_alone_make_returns_rise_with_size() -> None:
    """Without an absorption limit, bigger is simply better."""
    returns = [
        investment_metrics(**dict(EXAMPLE, capacity_mw=mw, scale_exponent=0.85))[
            "achieved_return"
        ]
        for mw in (200.0, 400.0, 800.0)
    ]
    assert returns == sorted(returns)


def test_without_a_scale_exponent_returns_are_flat_in_size() -> None:
    """The property this feature exists to break: every term is linear in
    capacity, so the ratio setting the return cancels it out."""
    returns = {
        investment_metrics(**dict(EXAMPLE, capacity_mw=mw))["achieved_return"]
        for mw in (200.0, 400.0, 600.0)
    }
    assert len(returns) == 1


def test_capacity_beyond_what_the_market_absorbs_earns_nothing() -> None:
    capped = investment_metrics(**dict(EXAMPLE, capacity_mw=800.0, absorption_mw=400.0))
    reference = investment_metrics(**dict(EXAMPLE, capacity_mw=400.0))
    assert capped["revenue"] == pytest.approx(reference["revenue"])
    assert capped["energy"] == pytest.approx(reference["energy"])
    # ...but the idle half is still built and still maintained.
    assert capped["fixed"]["total"] == pytest.approx(2 * reference["fixed"]["total"])


def test_an_absorption_limit_above_capacity_changes_nothing() -> None:
    assert investment_metrics(**dict(EXAMPLE, absorption_mw=5000.0)) == (
        investment_metrics(**EXAMPLE)
    )


# The sizing scenario the teaching notes ask a student to type in. Its whole
# point is that viability has an upper bound as well as a lower one, which the
# flat-$/kW model could never show: too small and scale economies have not
# arrived, too large and the extra capacity is unsellable.
SIZING_SCENARIO = dict(
    life_years=25, capex_per_kw=1400.0, wacc=0.07, fom_per_kw=25.0,
    fuel_price=9.5, efficiency_pct=33.0, vom=4.0,
    forced_outage_rate=0.08, planned_days=0.0,
    bands=[
        {"price": 45.0, "hours": 4000.0},
        {"price": 85.0, "hours": 3500.0},
        {"price": 220.0, "hours": 1160.0},
        {"price": 253.0, "hours": 100.0},
    ],
    scale_exponent=0.85, absorption_mw=1000.0,
)


@pytest.mark.parametrize("capacity_mw,expected_return,viable", [
    (400.0, 5.88, False),
    (600.0, 6.53, False),
    (800.0, 7.00, True),
    (1000.0, 7.38, True),
    (1200.0, 5.21, False),
])
def test_the_sizing_scenario_is_viable_only_between_800_and_1000_mw(
    capacity_mw: float, expected_return: float, viable: bool
) -> None:
    m = investment_metrics(capacity_mw=capacity_mw, **SIZING_SCENARIO)
    assert m["achieved_return"] * 100 == pytest.approx(expected_return, abs=0.02)
    assert m["is_viable"] is viable


def test_the_sizing_scenario_peaks_at_the_absorption_limit() -> None:
    """Returns rise to the limit, then fall — the shape is the lesson."""
    returns = [
        investment_metrics(capacity_mw=mw, **SIZING_SCENARIO)["achieved_return"]
        for mw in (400.0, 700.0, 1000.0, 1300.0, 1600.0)
    ]
    peak = returns.index(max(returns))
    assert peak == 2, "the peak must sit at the 1000 MW absorption limit"
    assert returns[:3] == sorted(returns[:3])
    assert returns[2:] == sorted(returns[2:], reverse=True)
