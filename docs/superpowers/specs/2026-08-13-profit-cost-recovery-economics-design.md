# Profit & Fixed Cost Recovery: show the whole economic picture

**Date:** 2026-08-13
**Status:** approved design, not yet implemented
**Touches:** `experiments/profit_cost_recovery.py` only

## Problem

A student working through the experiment cannot answer three basic questions:

**Where does the market price come from?** It is a hidden three-step function
of the plant's own marginal cost
([`profit_cost_recovery.py:19-24`](../../../experiments/profit_cost_recovery.py)):

```python
if marginal_cost <= 50:      avg_market_price = 75
elif marginal_cost <= 150:   avg_market_price = 180
else:                        avg_market_price = 500
```

Nothing on screen says this. Moving marginal cost from 50 to 51 jumps the
assumed price from $75 to $180/MWh and revenue leaps with it, for no visible
reason. The single most important number in the revenue calculation is both
invisible and self-moving.

**What is CAPEX, and what are its components?** There is no CAPEX in the model.
There is one input, "Annual Fixed Cost ($M)", with no build-up behind it.

**What is OPEX?** Also absent as a concept. There is one "Marginal Cost
($/MWh)" input, with fuel, efficiency and variable O&M collapsed into it, and
no fixed O&M at all.

Two defects follow from the same thinness:

1. **The "Fixed Cost" bar is not fixed cost.** Line 112 computes it as
   `total_revenue - short_run_profit`, which is algebraically
   `total_variable_cost`. The chart plots variable cost twice and never plots
   fixed cost.
2. **The rate of return has no investment in it.** Line 36 uses
   `fixed_cost_annual * (1 + required_ror)` and line 41 divides by
   `fixed_cost_annual`. A required return is earned on capital invested, not on
   one year of costs. "Actual RoR" is therefore not a rate of return on
   anything.

## Goals

1. Every number a student can see is traceable to something they typed.
2. CAPEX and OPEX exist as real, decomposed quantities.
3. The market price is an explicit input, not a hidden function of the plant.
4. Fix defects 1 and 2 by construction rather than by patch.

## Non-goals

- No change to any other experiment. This is one file.
- No coupling to the Pool Market Pricing experiment. Reusing its clearing
  prices was considered and rejected: it would tie two experiments together,
  against the isolation the standalone-experiments restructure just bought.
- No technology presets (CCGT/OCGT/coal/solar) in this change. Worth doing
  later; it needs defensible sourced figures or students trust them blindly.

## Design

### Inputs

| Group | Inputs |
|---|---|
| Plant | Capacity (MW), technical life (years) |
| CAPEX | Overnight cost ($/kW), WACC (%) |
| Fixed OPEX | Fixed O&M ($/kW/yr) |
| Variable OPEX | Fuel price ($/GJ), thermal efficiency (%), variable O&M ($/MWh) |
| Availability | Forced outage rate (%), planned maintenance (days/yr) |
| Market | Price-duration curve: four editable bands of (price $/MWh, hours) |

The price-duration table is an editable four-row grid with a live check that
the hours sum to 8760. Defaults: 45 $/MWh × 4000 h, 85 × 3500, 220 × 1160,
800 × 100.

### The calculation chain

```
marginal cost    = fuel_price × (3.6 / efficiency) + VOM            [$/MWh]
capital recovery = CRF(r, n) = r(1+r)ⁿ / ((1+r)ⁿ − 1)
annual fixed     = CAPEX_per_kW × capacity_kW × CRF(WACC, life)
                   + FOM_per_kW × capacity_kW
available hours  = per band, after outages (see below)
running hours    = available hours in bands where price > marginal cost
energy           = capacity × running hours                          [MWh]
revenue          = Σ band price × band energy
short-run profit = Σ (band price − marginal cost) × band energy   ← scarcity rent
long-run profit  = short-run profit − annual fixed
capacity factor  = energy / (capacity × 8760)                     ← an OUTPUT
```

Capacity factor stops being an input. It is a consequence of the price curve,
the plant's marginal cost and its availability, which is the point: a student
cannot dial in a comfortable number, they have to earn it.

### Availability: two distinct effects

A thermal plant misses hours for mechanical reasons regardless of price, and
the two kinds of unavailability behave differently:

- **Forced outages** are random, so the forced outage rate scales every band
  down equally.
- **Planned maintenance** is scheduled, so its days are taken out of the
  lowest-price bands first — what an operator actually does.

The consequence is worth seeing: maintenance lands in hours the plant would
not have run anyway, so it costs almost no revenue. Scheduling outages is an
economic decision, and this makes that legible without adding a control.

### Rate of return

Required return is the WACC input, which already sits inside the CRF. Achieved
return is the discount rate at which the project breaks even: for a flat annual
cash flow that is exact, found by bisection on `CRF(r, life) × CAPEX = annual
cash flow to capital`, where that cash flow is short-run profit less fixed O&M.

Viability then reads two consistent ways — long-run profit ≥ 0, and achieved ≥
required — because they are the same statement.

### What the student sees

Inputs are grouped so the cost build-up reads top to bottom: Plant → CAPEX →
Fixed O&M → Variable cost → Availability → Market.

Two charts replace the present 2×2 panel. The viability gauge goes (it says
less than the number beside it) and so does the operating/idle pie (the first
chart tells it better).

1. **Price-duration curve** with the marginal-cost line drawn across it, the
   hours the plant runs shaded, and the area between price and marginal cost
   shaded as scarcity rent. This is the chart that answers the original
   question: which hours pay for this plant.
2. **Waterfall**: revenue → less variable cost → short-run profit → less
   annualised CAPEX → less fixed O&M → long-run profit. Every bar is a real
   quantity, which is what defect 1 was hiding.

**A cost build-up table** shows each component in both its input unit and in
dollars — `900 $/kW × 400 MW = $360.0M`, `× CRF 0.0858 = $30.9M/yr` — so any
number traces back to an input.

Metrics keep their place: marginal cost, annual fixed cost, derived capacity
factor, short- and long-run profit, achieved vs required return, viability.
The "Analyze Investment" scenario table stays and gains the new columns.

### Structure and testing

The calculation becomes small pure functions, with `render()` doing only
layout:

- `capital_recovery_factor(rate, years) -> float`
- `marginal_cost(fuel_price, efficiency_pct, vom) -> float`
- `annual_fixed_cost(capex_per_kw, capacity_mw, wacc, life, fom_per_kw) -> dict`
- `dispatch(bands, marginal_cost, forced_outage_rate, planned_days) -> list`
- `achieved_return(capex, annual_cash_flow, life) -> float`

Tests (`tests/test_profit_cost_recovery.py`):

- CRF against a hand-checked value: `CRF(0.07, 25) = 0.08581`
- planned maintenance is drawn from the cheapest bands first, and forced
  outages scale all bands equally
- the worked example below, end to end
- degenerate cases: no band priced above marginal cost (zero revenue, zero
  running hours, long-run profit = −annual fixed), zero CAPEX, 100% availability
- `achieved_return` round-trips: `CRF(achieved, life) × capex == cash flow`

### Acceptance: the worked example

400 MW, 900 $/kW, WACC 7% over 25 years, FOM 25 $/kW/yr, fuel 9.5 $/GJ at 33%
efficiency, VOM $4/MWh, forced outage rate 8%, bands as defaulted above:

| Quantity | Expected |
|---|---|
| Marginal cost | $107.6/MWh |
| Annualised CAPEX | $30.9M/yr |
| Annual fixed cost | $40.9M/yr |
| Bands in merit | peak (220) and scarcity (800) only |
| Running hours | 1 159 h |
| Revenue | $123.4M |
| Variable cost | $49.9M |
| Short-run profit | $73.4M |
| Long-run profit | +$32.6M |
| Capacity factor | 13.2% |
| Achieved return | 17.3% against 7% required |

(Computed and checked against this design, not estimated — the implementation
must reproduce these to the stated precision.)

The teaching point the current version cannot make: this plant is viable while
running 13% of the year, and the 92 available scarcity hours — 1% of the year —
supply **78%** of its long-run profit. Remove the scarcity band and the plant
still clears $7.07M, so the lesson is the concentration of the return, not a
sign flip. (An earlier draft of this spec claimed removal made it unviable;
that was checked and is false.)

### Educational content

The existing expander keeps its Chapter 2.11 framing and gains: what CAPEX and
OPEX are and how each reaches the annual accounts; why fixed costs can only be
recovered from short-run profit; why a peaker's viability rests on a handful of
hours; and why maintenance scheduling is an economic decision.

## Consequence for the test suite

This deliberately changes what the experiment renders, so
`tests/test_extraction_faithful.py` will fail on `profit_cost_recovery`. That
is the designed behaviour of that gate, and the first real use of the refresh
workflow:

```bash
.venv/bin/python scripts/refresh_baseline.py --check   # read the diff
.venv/bin/python scripts/refresh_baseline.py           # accept it
```

Only `profit_cost_recovery` may appear in that diff. Any other experiment
showing up means something leaked, and is a defect to investigate rather than
accept.
