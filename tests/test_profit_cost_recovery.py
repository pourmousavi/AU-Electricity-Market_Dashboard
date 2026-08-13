"""The economics behind Profit & Fixed Cost Recovery.

Every figure here is hand-checked against the worked example in
docs/superpowers/specs/2026-08-13-profit-cost-recovery-economics-design.md.
"""
import pytest

from experiments.profit_cost_recovery import (
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
