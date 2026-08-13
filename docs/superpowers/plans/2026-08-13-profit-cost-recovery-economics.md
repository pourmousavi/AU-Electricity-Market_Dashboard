# Profit & Fixed Cost Recovery Economics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Profit & Fixed Cost Recovery experiment a real cost model — decomposed CAPEX and OPEX, a student-defined price-duration curve, and outage modelling — so every number on screen traces back to an input.

**Architecture:** The economics move out of the UI into small pure functions at the top of the module, each independently testable without Streamlit; `render()` becomes layout only. The hidden marginal-cost-driven price heuristic is replaced by an editable price-duration table, and capacity factor changes from an input dial to a derived output.

**Tech Stack:** Python 3.12, Streamlit (>=1.55,<1.62), plotly (`go.Waterfall`, `go.Scatter`), pandas, pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-profit-cost-recovery-economics-design.md` — read it first; this plan argues from it.

## Global Constraints

- One experiment file changes: `experiments/profit_cost_recovery.py`. No other experiment, no `experiments/_kit/`, no `hub/`.
- The module must keep exposing `render() -> None` and must never call `st.set_page_config`.
- It must NOT declare `STATE_GROUP` — `profit_cost_recovery` is its own state group. `tests/test_experiments_render.py::test_ungrouped_experiments_declare_no_state_group` enforces this.
- Widget keys keep the existing `profit_` prefix so nothing collides.
- Heat rate conversion is exactly `3.6 / efficiency_fraction` GJ/MWh. Capital recovery factor is exactly `r(1+r)ⁿ / ((1+r)ⁿ − 1)`.
- The acceptance figures in the spec's worked example are computed, not estimated. The implementation must reproduce them: CRF(0.07, 25) = 0.08581, marginal cost $107.6/MWh, annual fixed $40.9M, 1 159 running hours, revenue $123.4M, short-run profit $73.4M, long-run profit +$32.6M, capacity factor 13.2%, achieved return 17.3%.
- Default price bands: 45 $/MWh × 4000 h, 85 × 3500, 220 × 1160, 800 × 100.
- Tests run with `.venv/bin/python -m pytest` from the repo root. The suite currently passes at 200.
- No dependency additions or upgrades.
- `tests/test_extraction_faithful.py` WILL fail on `profit_cost_recovery` from Task 2 onward — that is by design and is resolved in Task 5, not by weakening the test. Do not touch `tests/baseline_render.json` before Task 5.
- End every commit message body with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

### Task 1: The economics, as pure functions

Everything the UI will need, with no Streamlit involved, so it can be tested directly.

**Files:**
- Modify: `experiments/profit_cost_recovery.py` (add functions above `render()`; leave `render()` and the old `calculate_investment_metrics` alone for now)
- Create: `tests/test_profit_cost_recovery.py`

**Interfaces:**
- Produces, all consumed by Tasks 2–4:
  - `capital_recovery_factor(rate: float, years: int) -> float`
  - `marginal_cost(fuel_price: float, efficiency_pct: float, vom: float) -> float`
  - `annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw) -> dict` with keys `capex_total`, `crf`, `annualised_capex`, `fixed_om`, `total`
  - `dispatch(bands, marginal_cost_value, forced_outage_rate, planned_days) -> list[dict]` where `bands` is `[{"price": float, "hours": float}, ...]` and each returned dict has `price`, `hours`, `available_hours`, `running_hours`
  - `achieved_return(capex_total: float, annual_cash_flow: float, life_years: int) -> float | None`
  - `investment_metrics(...) -> dict` — the single call `render()` makes; keys listed in Step 5

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profit_cost_recovery.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_profit_cost_recovery.py -q`
Expected: collection error — `ImportError: cannot import name 'achieved_return'`.

- [ ] **Step 3: Write the implementation**

In `experiments/profit_cost_recovery.py`, directly below the imports and ABOVE the existing `calculate_investment_metrics`:

```python
# --- Economics -------------------------------------------------------------
#
# Pure functions: numbers in, numbers out, no Streamlit. Everything the page
# displays is derived here so a student can trace any figure on screen back to
# an input, and so the model can be tested without rendering anything.

GJ_PER_MWH = 3.6
HOURS_PER_YEAR = 8760


def capital_recovery_factor(rate: float, years: int) -> float:
    """The fraction of capital that must be repaid each year.

    Turns an up-front CAPEX into the level annual payment that repays it over
    `years` while earning `rate` on the outstanding balance -- which is what
    makes an overnight cost comparable with a year of revenue.
    """
    if rate == 0:
        return 1.0 / years
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def marginal_cost(fuel_price: float, efficiency_pct: float, vom: float) -> float:
    """Short-run cost of one more MWh, in $/MWh.

    A MWh is 3.6 GJ of energy, so a plant at `efficiency_pct` burns
    3.6/efficiency GJ of fuel to deliver it.
    """
    heat_rate = GJ_PER_MWH / (efficiency_pct / 100)
    return fuel_price * heat_rate + vom


def annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw) -> dict:
    """Annualised CAPEX and fixed O&M, each kept separate for display."""
    capacity_kw = capacity_mw * 1000
    capex_total = capex_per_kw * capacity_kw
    crf = capital_recovery_factor(wacc, life_years)
    annualised_capex = capex_total * crf
    fixed_om = fom_per_kw * capacity_kw
    return {
        "capex_total": capex_total,
        "crf": crf,
        "annualised_capex": annualised_capex,
        "fixed_om": fixed_om,
        "total": annualised_capex + fixed_om,
    }


def dispatch(bands, marginal_cost_value, forced_outage_rate, planned_days) -> list:
    """Hours per price band after outages, and which of them are in merit.

    The two kinds of unavailability behave differently, and the difference is
    worth seeing:

    * Forced outages are random, so they scale every band down equally.
    * Planned maintenance is scheduled, so an operator takes it in the
      cheapest hours first -- which is why maintenance costs a peaker almost
      no revenue, and why outage scheduling is an economic decision.
    """
    available = [band["hours"] * (1 - forced_outage_rate) for band in bands]

    remaining = planned_days * 24
    for index in sorted(range(len(bands)), key=lambda i: bands[i]["price"]):
        if remaining <= 0:
            break
        taken = min(available[index], remaining)
        available[index] -= taken
        remaining -= taken

    return [
        {
            "price": band["price"],
            "hours": band["hours"],
            "available_hours": hours,
            "running_hours": hours if band["price"] > marginal_cost_value else 0.0,
        }
        for band, hours in zip(bands, available)
    ]


def achieved_return(capex_total: float, annual_cash_flow: float,
                    life_years: int) -> float | None:
    """The return the capital actually earns, or None if it never repays.

    For a flat annual cash flow this is exact: find the rate whose recovery
    factor turns this CAPEX into exactly this cash flow. Bisection, because
    the closed form does not exist and the factor rises monotonically in rate.
    """
    if capex_total <= 0 or annual_cash_flow <= 0:
        return None
    if annual_cash_flow * life_years <= capex_total:
        return None  # does not even return the capital, let alone a profit

    low, high = 0.0, 10.0
    for _ in range(200):
        mid = (low + high) / 2
        if capital_recovery_factor(mid, life_years) * capex_total < annual_cash_flow:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def investment_metrics(capacity_mw, life_years, capex_per_kw, wacc, fom_per_kw,
                       fuel_price, efficiency_pct, vom, forced_outage_rate,
                       planned_days, bands) -> dict:
    """Everything the page displays, from what the student typed."""
    mc = marginal_cost(fuel_price, efficiency_pct, vom)
    fixed = annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life_years, fom_per_kw)
    dispatched = dispatch(bands, mc, forced_outage_rate, planned_days)

    running_hours = sum(band["running_hours"] for band in dispatched)
    energy = capacity_mw * running_hours
    revenue = sum(band["price"] * capacity_mw * band["running_hours"]
                  for band in dispatched)
    variable_cost = mc * energy
    short_run_profit = revenue - variable_cost
    long_run_profit = short_run_profit - fixed["total"]

    return {
        "marginal_cost": mc,
        "fixed": fixed,
        "dispatched": dispatched,
        "running_hours": running_hours,
        "energy": energy,
        "revenue": revenue,
        "variable_cost": variable_cost,
        "short_run_profit": short_run_profit,
        "long_run_profit": long_run_profit,
        "capacity_factor": 100 * energy / (capacity_mw * HOURS_PER_YEAR),
        "required_return": wacc,
        "achieved_return": achieved_return(
            fixed["capex_total"], short_run_profit - fixed["fixed_om"], life_years
        ),
        "is_viable": long_run_profit >= 0,
    }
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_profit_cost_recovery.py -v`
Expected: 14 passed.

If `test_the_worked_example_end_to_end` fails on `running_hours`, check that forced outage rate is applied to ALL bands before the in-merit filter, not only to the ones that run.

- [ ] **Step 5: Confirm nothing else moved yet**

Run: `.venv/bin/python -m pytest -q`
Expected: 214 passed. `tests/test_extraction_faithful.py` still passes because `render()` has not changed.

- [ ] **Step 6: Commit**

```bash
git add experiments/profit_cost_recovery.py tests/test_profit_cost_recovery.py
git commit -m "feat: add a real cost model to profit cost recovery

CAPEX annualised through the capital recovery factor, OPEX split into fuel,
efficiency and O&M, and dispatch driven by a price-duration curve with forced
and planned outages handled separately. Pure functions, no UI yet."
```

---

### Task 2: The inputs and the cost build-up

Replace the old input block. After this task the page reads from the new model.

**Files:**
- Modify: `experiments/profit_cost_recovery.py` — `render()`, and delete `calculate_investment_metrics` (superseded by `investment_metrics`)

**Interfaces:**
- Consumes: `investment_metrics(...)` from Task 1.
- Produces: `_price_bands(edited: pd.DataFrame) -> list[dict]` — converts the edited band table into `[{"price": float, "hours": float}, ...]`, the shape `dispatch()` and `investment_metrics()` expect.

- [ ] **Step 1: Delete the superseded function**

Delete `calculate_investment_metrics` entirely (the whole `def`, lines 12–58 of the original file). Its price heuristic is the defect this work exists to remove; leaving it would leave a second, contradictory model in the file.

- [ ] **Step 2: Add the band editor helper**

Above `render()`:

```python
DEFAULT_BANDS = [
    {"Band": "Off-peak", "Price ($/MWh)": 45.0, "Hours/year": 4000.0},
    {"Band": "Shoulder", "Price ($/MWh)": 85.0, "Hours/year": 3500.0},
    {"Band": "Peak", "Price ($/MWh)": 220.0, "Hours/year": 1160.0},
    {"Band": "Scarcity", "Price ($/MWh)": 800.0, "Hours/year": 100.0},
]


def _price_bands(edited) -> list:
    """The edited price-duration table as the model wants it."""
    return [
        {"price": float(row["Price ($/MWh)"]), "hours": float(row["Hours/year"])}
        for row in edited.to_dict("records")
    ]
```

- [ ] **Step 3: Replace the input block**

In `render()`, replace everything from `capacity = st.slider(...)` down to and including the `metrics = calculate_investment_metrics(...)` line with:

```python
        st.markdown("**Plant**")
        capacity = st.slider("Capacity (MW)", 100, 1000, 400, 50, key="profit_capacity")
        life_years = st.slider("Technical life (years)", 10, 40, 25, 5,
                               key="profit_life")

        st.markdown("**Capital**")
        capex_per_kw = st.number_input(
            "Overnight capital cost ($/kW)", 100, 6000, 900, 50,
            key="profit_capex",
            help="What it costs to build, per kW of capacity, before financing.",
        )
        wacc = st.slider("WACC — required return (%)", 3.0, 15.0, 7.0, 0.5,
                         key="profit_wacc") / 100

        st.markdown("**Operating cost**")
        fom_per_kw = st.number_input("Fixed O&M ($/kW/year)", 0, 200, 25, 5,
                                     key="profit_fom",
                                     help="Staff, insurance, overhauls — paid whether or not the plant runs.")
        fuel_price = st.number_input("Fuel price ($/GJ)", 0.0, 40.0, 9.5, 0.5,
                                     key="profit_fuel")
        efficiency_pct = st.slider("Thermal efficiency (%)", 20.0, 62.0, 33.0, 1.0,
                                   key="profit_eff",
                                   help="Higher efficiency means less fuel per MWh.")
        vom = st.number_input("Variable O&M ($/MWh)", 0.0, 30.0, 4.0, 0.5,
                              key="profit_vom")

        st.markdown("**Availability**")
        forced_outage_rate = st.slider("Forced outage rate (%)", 0.0, 30.0, 8.0, 1.0,
                                       key="profit_for",
                                       help="Unplanned breakdowns. Random, so they cost hours in every price band.") / 100
        planned_days = st.slider("Planned maintenance (days/year)", 0, 90, 0, 7,
                                 key="profit_planned",
                                 help="Scheduled, so it is taken in the cheapest hours first.")

        st.markdown("**Market prices**")
        st.caption(
            "The price-duration curve: how many hours a year sit at each price. "
            "The plant runs only where the price beats its marginal cost."
        )
        edited = st.data_editor(
            pd.DataFrame(DEFAULT_BANDS), key="profit_bands",
            num_rows="fixed", use_container_width=True,
        )
        bands = _price_bands(edited)

        total_band_hours = sum(band["hours"] for band in bands)
        if abs(total_band_hours - 8760) > 1:
            st.warning(
                f"The bands cover {total_band_hours:,.0f} hours; a year is 8,760. "
                "Results are still shown, but the capacity factor will not mean much."
            )

        metrics = investment_metrics(
            capacity_mw=capacity, life_years=life_years,
            capex_per_kw=capex_per_kw, wacc=wacc, fom_per_kw=fom_per_kw,
            fuel_price=fuel_price, efficiency_pct=efficiency_pct, vom=vom,
            forced_outage_rate=forced_outage_rate, planned_days=planned_days,
            bands=bands,
        )
```

- [ ] **Step 4: Add the cost build-up table**

Immediately after the `metrics = investment_metrics(...)` call:

```python
        st.markdown("**Where the numbers come from**")
        fixed = metrics["fixed"]
        st.dataframe(pd.DataFrame([
            {"Component": "Overnight CAPEX",
             "Working": f"{capex_per_kw:,.0f} $/kW × {capacity:,.0f} MW",
             "Result": f"${fixed['capex_total']/1e6:,.1f}M"},
            {"Component": "Capital recovery factor",
             "Working": f"{wacc*100:.1f}% over {life_years} years",
             "Result": f"{fixed['crf']:.4f}"},
            {"Component": "Annualised CAPEX",
             "Working": f"${fixed['capex_total']/1e6:,.1f}M × {fixed['crf']:.4f}",
             "Result": f"${fixed['annualised_capex']/1e6:,.1f}M/yr"},
            {"Component": "Fixed O&M",
             "Working": f"{fom_per_kw:,.0f} $/kW/yr × {capacity:,.0f} MW",
             "Result": f"${fixed['fixed_om']/1e6:,.1f}M/yr"},
            {"Component": "Annual fixed cost",
             "Working": "annualised CAPEX + fixed O&M",
             "Result": f"${fixed['total']/1e6:,.1f}M/yr"},
            {"Component": "Fuel cost",
             "Working": f"{fuel_price:,.2f} $/GJ ÷ {efficiency_pct:.0f}% efficiency",
             "Result": f"${fuel_price * 3.6 / (efficiency_pct/100):,.1f}/MWh"},
            {"Component": "Marginal cost",
             "Working": f"fuel + {vom:,.1f} $/MWh variable O&M",
             "Result": f"${metrics['marginal_cost']:,.1f}/MWh"},
        ]), use_container_width=True, hide_index=True)
```

- [ ] **Step 5: Update the right-hand metrics**

Replace the five `st.metric(...)` calls under `st.subheader("Current Scenario")` with:

```python
        st.metric("Investment Viability",
                  "✅ VIABLE" if metrics["is_viable"] else "❌ NOT VIABLE")
        st.metric("Marginal cost", f"${metrics['marginal_cost']:,.1f}/MWh")
        st.metric("Annual fixed cost", f"${metrics['fixed']['total']/1e6:,.1f}M")
        st.metric("Capacity factor (derived)", f"{metrics['capacity_factor']:.1f}%",
                  help="An outcome, not a setting: the hours this plant is both available and in merit.")
        st.metric("Short-run profit", f"${metrics['short_run_profit']/1e6:,.1f}M",
                  help="Revenue less variable cost — the scarcity rent available to cover fixed costs.")
        st.metric("Long-run profit", f"${metrics['long_run_profit']/1e6:,.1f}M")
        achieved = metrics["achieved_return"]
        st.metric(
            "Return on capital",
            "never repays" if achieved is None else f"{achieved*100:.1f}%",
            help=f"Against {metrics['required_return']*100:.1f}% required.",
        )
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_profit_cost_recovery.py tests/test_experiments_render.py -q`
Expected: all pass — the experiment still renders and leaks no sibling content.

Run: `.venv/bin/python -m pytest -q`
Expected: exactly one failure, `test_extracted_module_renders_its_baseline_text[profit_cost_recovery]`. That is the designed behaviour from the Global Constraints. Any OTHER failure is a real defect — fix it before continuing.

- [ ] **Step 7: Commit**

```bash
git add experiments/profit_cost_recovery.py
git commit -m "feat: put CAPEX, OPEX and market prices on the page

Every input a student would ask about is now theirs to set, and the build-up
table shows each figure's working. Capacity factor becomes a derived output.
Deletes the marginal-cost-driven price heuristic that made revenue jump
invisibly at MC 50."
```

---

### Task 3: The two charts

**Files:**
- Modify: `experiments/profit_cost_recovery.py` — replace `create_profit_analysis_plot`

**Interfaces:**
- Consumes: the `metrics` dict from Task 1.
- Produces: `create_price_duration_plot(metrics) -> go.Figure`, `create_waterfall_plot(metrics) -> go.Figure`.

- [ ] **Step 1: Delete the old plot function**

Delete `create_profit_analysis_plot` entirely. Its "Fixed Cost" bar computed `total_revenue - short_run_profit`, which is variable cost — the defect named in the spec. There is nothing in it worth keeping.

- [ ] **Step 2: Write the price-duration chart**

```python
def create_price_duration_plot(metrics) -> go.Figure:
    """The price-duration curve, with the hours this plant runs shaded.

    This is the chart that answers "which hours pay for the plant". Bands are
    ordered dearest first, the classic price-duration shape, with marginal cost
    drawn across it: everything above the line and inside a shaded block is
    scarcity rent.
    """
    ordered = sorted(metrics["dispatched"], key=lambda band: -band["price"])
    mc = metrics["marginal_cost"]
    fig = go.Figure()

    cursor = 0.0
    xs, ys = [], []
    for band in ordered:
        xs += [cursor, cursor + band["hours"]]
        ys += [band["price"], band["price"]]
        if band["running_hours"] > 0:
            fig.add_trace(go.Scatter(
                x=[cursor, cursor + band["running_hours"],
                   cursor + band["running_hours"], cursor, cursor],
                y=[mc, mc, band["price"], band["price"], mc],
                fill="toself", fillcolor="rgba(78, 205, 196, 0.35)",
                mode="none", showlegend=False,
                hovertemplate=(
                    f"${band['price']:,.0f}/MWh for "
                    f"{band['running_hours']:,.0f} h<br>"
                    f"margin ${band['price'] - mc:,.0f}/MWh<extra></extra>"
                ),
            ))
        cursor += band["hours"]

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", name="Price-duration curve",
        line=dict(color="#1f77b4", width=3),
        hovertemplate="%{y:$,.0f}/MWh<extra></extra>",
    ))
    fig.add_hline(
        y=mc, line_dash="dash", line_color="#FF6B6B",
        annotation_text=f"marginal cost ${mc:,.0f}/MWh",
        annotation_position="top right",
    )
    fig.update_layout(
        title="When does this plant run, and what does it earn?",
        xaxis_title="Hours per year (dearest first)",
        yaxis_title="Price ($/MWh)",
        height=420, hovermode="closest",
    )
    return fig
```

- [ ] **Step 3: Write the waterfall**

```python
def create_waterfall_plot(metrics) -> go.Figure:
    """Revenue down to long-run profit, one bar per real quantity."""
    fixed = metrics["fixed"]
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "total", "relative", "relative", "total"],
        x=["Revenue", "Variable cost", "Short-run profit",
           "Annualised CAPEX", "Fixed O&M", "Long-run profit"],
        y=[metrics["revenue"] / 1e6, -metrics["variable_cost"] / 1e6, 0,
           -fixed["annualised_capex"] / 1e6, -fixed["fixed_om"] / 1e6, 0],
        text=[f"${metrics['revenue']/1e6:,.1f}M",
              f"−${metrics['variable_cost']/1e6:,.1f}M",
              f"${metrics['short_run_profit']/1e6:,.1f}M",
              f"−${fixed['annualised_capex']/1e6:,.1f}M",
              f"−${fixed['fixed_om']/1e6:,.1f}M",
              f"${metrics['long_run_profit']/1e6:,.1f}M"],
        textposition="outside",
        connector={"line": {"color": "rgba(0,0,0,0.3)"}},
        increasing={"marker": {"color": "#4ECDC4"}},
        decreasing={"marker": {"color": "#FF6B6B"}},
        totals={"marker": {"color": "#1f77b4"}},
    ))
    fig.update_layout(
        title="From revenue to long-run profit",
        yaxis_title="$M per year", height=420, showlegend=False,
    )
    return fig
```

- [ ] **Step 4: Render them**

Replace the old `fig = create_profit_analysis_plot(...)` / `st.plotly_chart(...)` pair with:

```python
        st.plotly_chart(create_price_duration_plot(metrics),
                        use_container_width=True, key="profit_duration_plot")
        st.plotly_chart(create_waterfall_plot(metrics),
                        use_container_width=True, key="profit_waterfall_plot")
```

- [ ] **Step 5: Add a test that the waterfall's arithmetic closes**

Append to `tests/test_profit_cost_recovery.py`:

```python
def test_the_waterfall_adds_up_to_long_run_profit() -> None:
    """A waterfall that does not close is worse than no waterfall."""
    from experiments.profit_cost_recovery import create_waterfall_plot

    m = investment_metrics(**EXAMPLE)
    steps = create_waterfall_plot(m).data[0].y
    revenue, less_variable, _, less_capex, less_fom, _ = steps
    assert revenue + less_variable + less_capex + less_fom == pytest.approx(
        m["long_run_profit"] / 1e6
    )
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_profit_cost_recovery.py -v`
Expected: 15 passed.

Run: `.venv/bin/python -m pytest -q`
Expected: still exactly the one expected `test_extraction_faithful` failure on `profit_cost_recovery`.

- [ ] **Step 7: Commit**

```bash
git add experiments/profit_cost_recovery.py tests/test_profit_cost_recovery.py
git commit -m "feat: show which hours pay for the plant

A price-duration curve with marginal cost across it and the running hours
shaded, plus a waterfall from revenue to long-run profit. Replaces the 2x2
panel whose 'Fixed Cost' bar was plotting variable cost."
```

---

### Task 4: Scenario table and educational content

**Files:**
- Modify: `experiments/profit_cost_recovery.py` — the "Analyze Investment" button, the results table, the insights block, the educational expander

- [ ] **Step 1: Record the new fields when a scenario is saved**

Replace the `st.session_state.profit_analysis_data.append({...})` payload with:

```python
            st.session_state.profit_analysis_data.append({
                "capacity": capacity,
                "marginal_cost": metrics["marginal_cost"],
                "capex_per_kw": capex_per_kw,
                "annual_fixed": metrics["fixed"]["total"],
                "capacity_factor": metrics["capacity_factor"],
                "running_hours": metrics["running_hours"],
                "revenue": metrics["revenue"],
                "variable_cost": metrics["variable_cost"],
                "short_run_profit": metrics["short_run_profit"],
                "long_run_profit": metrics["long_run_profit"],
                "required_return": metrics["required_return"],
                "achieved_return": metrics["achieved_return"],
                "is_viable": metrics["is_viable"],
            })
```

- [ ] **Step 2: Rebuild the results table**

Replace the `table_data.append({...})` payload with:

```python
                table_data.append({
                    "Scenario": i + 1,
                    "MW": point["capacity"],
                    "CAPEX ($/kW)": f"{point['capex_per_kw']:,.0f}",
                    "MC ($/MWh)": f"{point['marginal_cost']:,.1f}",
                    "Fixed ($M/yr)": f"{point['annual_fixed']/1e6:,.1f}",
                    "Run hours": f"{point['running_hours']:,.0f}",
                    "CF (%)": f"{point['capacity_factor']:.1f}",
                    "Revenue ($M)": f"{point['revenue']/1e6:,.1f}",
                    "SR profit ($M)": f"{point['short_run_profit']/1e6:,.1f}",
                    "LR profit ($M)": f"{point['long_run_profit']/1e6:,.1f}",
                    "Required (%)": f"{point['required_return']*100:.1f}",
                    "Achieved (%)": ("—" if point["achieved_return"] is None
                                     else f"{point['achieved_return']*100:.1f}"),
                    "Viable": "✅" if point["is_viable"] else "❌",
                })
```

- [ ] **Step 3: Rewrite the insights block**

Replace the `if latest['marginal_cost'] > 500:` chain and the RoR comparison beneath it with:

```python
                latest = st.session_state.profit_analysis_data[-1]

                if latest["running_hours"] == 0:
                    st.error(
                        "🚫 This plant never runs: no price band beats its marginal "
                        f"cost of ${latest['marginal_cost']:,.0f}/MWh. It loses its "
                        f"whole fixed cost of ${latest['annual_fixed']/1e6:,.1f}M."
                    )
                elif latest["capacity_factor"] < 20:
                    st.info(
                        f"🔥 A peaking profile: {latest['capacity_factor']:.1f}% "
                        f"capacity factor over {latest['running_hours']:,.0f} hours. "
                        "Most of the profit comes from the dearest band — set its "
                        "hours to zero and watch how much of it goes."
                    )
                elif latest["capacity_factor"] > 70:
                    st.success(
                        f"🌱 A baseload profile: running {latest['capacity_factor']:.1f}% "
                        "of the year on low marginal cost."
                    )

                if latest["achieved_return"] is None:
                    st.error("📉 The capital is never repaid at any discount rate.")
                elif latest["achieved_return"] < latest["required_return"]:
                    gap = (latest["required_return"] - latest["achieved_return"]) * 100
                    st.error(f"📉 Returns {gap:.1f} points below the {latest['required_return']*100:.1f}% required.")
                else:
                    gap = (latest["achieved_return"] - latest["required_return"]) * 100
                    st.success(f"📈 Returns {gap:.1f} points above the {latest['required_return']*100:.1f}% required.")
```

- [ ] **Step 4: Extend the educational content**

Inside the existing `st.expander("📚 Educational Content")`, insert this immediately after the `### Profit and Fixed Cost Recovery (Chapter 2.11)` heading, keeping everything already there below it:

```python
        st.markdown("""
        **What the plant costs**

        - **CAPEX** is the overnight capital cost — what it costs to build,
          quoted per kW so plants of different sizes compare. It is paid once,
          so to set it against a year of revenue it is spread over the plant's
          life by the **capital recovery factor**, which also earns the
          investor's required return on the capital still outstanding.
        - **Fixed O&M** is staff, insurance and scheduled overhauls: paid every
          year whether the plant generates or not.
        - **Variable cost** is fuel divided by efficiency, plus variable O&M.
          This is the plant's **marginal cost**, and it decides when it runs.

        **What the plant earns**

        The price-duration curve says how many hours a year sit at each price.
        The plant runs only where price exceeds its marginal cost, and only
        when it is mechanically available. So capacity factor is an *outcome*
        of the market and the machine, never a number an investor chooses.

        **Why scarcity hours decide everything**

        In every hour it runs, the plant earns price minus marginal cost. That
        margin is **scarcity rent**, and it is the only thing available to pay
        back CAPEX and fixed O&M. With the defaults, the 100 scarcity hours are
        1% of the year and supply about 78% of the long-run profit: a hundred
        hours at $800/MWh contribute far more than thousands at $45. Set the
        scarcity band's hours to zero and watch most of the profit disappear.

        **Why outage scheduling is an economic decision**

        Forced outages are random, so they cost hours in every band, scarcity
        hours included. Planned maintenance is scheduled, so an operator takes
        it in the cheapest hours — where the plant would not have run anyway.
        Raise the maintenance days and see how little the profit moves; raise
        the forced outage rate by the same amount and see how much it does.
        """)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest -q`
Expected: still exactly the one expected `test_extraction_faithful` failure.

- [ ] **Step 6: Commit**

```bash
git add experiments/profit_cost_recovery.py
git commit -m "feat: explain the cost model in the scenario table and notes

Scenario rows carry the new quantities, the insights speak to capacity factor
and repayment rather than marginal-cost tiers, and the notes explain CAPEX,
scarcity rent and why outage scheduling is an economic decision."
```

---

### Task 5: Accept the new rendering, and verify in the app

**Files:**
- Modify: `tests/baseline_render.json` (regenerated, never hand-edited)

- [ ] **Step 1: Read what changed before accepting it**

Run: `.venv/bin/python scripts/refresh_baseline.py --check`

Expected: `profit_cost_recovery` appears in the list. Weeks 2, 3 and 4 experiments will also appear, dropping their sidebar-branding lines — that is the known first-refresh behaviour documented in `scripts/refresh_baseline.py`.

Any experiment OTHER than those is a defect: stop and investigate rather than accepting it.

- [ ] **Step 2: Accept it**

Run: `.venv/bin/python scripts/refresh_baseline.py`

- [ ] **Step 3: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green, 215 tests.

- [ ] **Step 4: Drive the real app**

Run: `.venv/bin/python -m streamlit run app.py`

Open Profit & Fixed Cost Recovery and confirm, by hand:
1. With the defaults, marginal cost reads ~$107.6/MWh, annual fixed ~$40.9M, capacity factor ~13.2%, long-run profit ~+$32.6M, return on capital ~17.3%.
2. Setting the scarcity band's hours to 0 drops long-run profit to ~+$7.1M — still viable, but 78% of the profit gone.
3. Raising planned maintenance to 60 days barely moves long-run profit; raising the forced outage rate from 8% to 20% moves it materially.
4. The waterfall's last bar equals the long-run profit metric.

- [ ] **Step 5: Commit**

```bash
git add tests/baseline_render.json
git commit -m "test: re-record the rendering baseline

profit_cost_recovery renders the new cost model; weeks 2-4 shed the sidebar
branding the split dropped, which is the first refresh's known diff."
```

---

## Notes for the implementer

- **The acceptance numbers are the spec's, and they are computed, not guessed.** If the end-to-end test disagrees with them, the implementation is wrong, not the test.
- **Do not reintroduce a price heuristic.** If a default feels wrong, change the default band values — never derive price from the plant's own marginal cost, which is the defect this work removes.
- **`use_container_width` is used throughout this file.** Keep using it: `requirements.txt` pins `streamlit<1.62` precisely because the experiments have not migrated, and a lone migration here would be inconsistent.
