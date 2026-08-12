"""Each extracted module must render what its bundled original rendered.

Tasks add a line to EXTRACTED as they extract. An experiment that is not in
this map yet is simply not checked -- the map grows to 25 by the end of the
split, and test_every_experiment_is_checked then locks it.
"""
import json
from collections import Counter
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
BASELINE = json.loads((ROOT / "tests" / "baseline_render.json").read_text())

# new id -> old id. One line added per extracted experiment.
EXTRACTED: dict[str, str] = {
    "consumer_model": "w2.consumer_model",
    "consumer_elasticity": "w2.consumer_elasticity",
    "supplier_model": "w2.supplier_model",
    "supplier_elasticity": "w2.supplier_elasticity",
    "market_equilibrium": "w2.market_equilibrium",
    "pool_pricing": "w3.pool_pricing",
    "market_power": "w3.market_power",
    "profit_cost_recovery": "w3.profit_cost_recovery",
    "interactive_clearing": "w3.interactive_clearing",
    "modelling_tools_comparison": "w4.tools_comparison",
    "nonlinear_optimisation_3d": "w4.nonlinear_3d",
    "strong_duality": "w6.strong_duality",
    "weak_duality": "w6.weak_duality",
    "duality_theorems": "w6.duality_theorems",
}


def _build_allowances() -> dict[str, Counter]:
    """Build per-experiment removal allowances based on OLD id.

    Week 2, 3, 4 have module-level sidebar branding that extraction removes.
    Week 6, 7, 8 have no sidebar branding removals - all content stays.
    """
    allowances: dict[str, Counter] = {}

    # Week 2: sidebar branding from sources/week2_consumer_supplier.py:32-50
    w2_allowance = Counter({
        "⚡ Electricity Market Dashboard": 1,
        "---": 4,  # 4 separate st.sidebar.markdown("---") calls
        "### Course Information": 1,
        "**Electricity Market and Power Systems Operation**": 1,
        "**ELEC ENG 4087/7087**": 1,
        "**Course Coordinator & Creator:**": 1,
        "Ali Pourmousavi Kani": 1,
        "**Version:** 2.0": 1,
    })

    # Week 3: sidebar branding from sources/week3_pricing_market_power.py:128-146
    w3_allowance = Counter({
        "⚡ Electricity Market Dashboard": 1,
        "---": 4,
        "### Course Information": 1,
        "**Electricity Market and Power Systems Operation**": 1,
        "**ELEC ENG 4087/7087**": 1,
        "**Course Coordinator & Creator:**": 1,
        "Ali Pourmousavi Kani": 1,
        "**Version:** 1.0 - Market Power & Economics": 1,
    })

    # Week 4: sidebar branding from sources/week4_optimisation_tools.py:16-36
    w4_allowance = Counter({
        "📈 3D Optimization Dashboard": 1,
        "---": 4,
        "### Course Information": 1,
        "**Electricity Market and Power Systems Operation**": 1,
        "**ELEC ENG 4087/7087**": 1,
        "**Course Coordinator & Creator:**": 1,
        "Ali Pourmousavi Kani": 1,
        "**Version:** 2.0 - 3D Nonlinear Optimization": 1,
    })

    # Week 6, 7, 8: no sidebar branding removals
    empty_allowance = Counter()

    # Assign allowances to experiments based on OLD id prefix
    for old_id in BASELINE.keys():
        if old_id.startswith("w2."):
            allowances[old_id] = w2_allowance.copy()
        elif old_id.startswith("w3."):
            allowances[old_id] = w3_allowance.copy()
        elif old_id.startswith("w4."):
            allowances[old_id] = w4_allowance.copy()
        else:  # w6, w7, w8
            allowances[old_id] = empty_allowance.copy()

    return allowances


ALLOWANCES = _build_allowances()


def _harness(new_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import importlib\n"
        f"module = importlib.import_module('experiments.{new_id}')\n"
        "module.render()\n"
    )


def _render(new_id: str):
    app = AppTest.from_string(_harness(new_id), default_timeout=180).run()
    assert not app.exception, (
        f"{new_id} raised: " + "; ".join(e.message for e in app.exception)
    )
    return app


@pytest.mark.parametrize("new_id", sorted(EXTRACTED))
def test_extracted_module_renders_its_baseline_text(new_id: str) -> None:
    app = _render(new_id)
    rendered_list = []
    for kind in ("title", "header", "subheader", "markdown", "info", "warning",
                 "error", "success", "caption", "code", "text"):
        for element in getattr(app, kind, []):
            value = getattr(element, "value", None)
            if isinstance(value, str):
                rendered_list.append(value)

    old_id = EXTRACTED[new_id]
    expected_counter = Counter(BASELINE[old_id]["text"])
    rendered_counter = Counter(rendered_list)
    allowance = ALLOWANCES[old_id]

    # Check for missing text: anything in baseline not in rendered (beyond allowance)
    missing_counter = expected_counter - rendered_counter
    if missing_counter:
        # Filter out allowed removals
        actual_missing = Counter()
        for text, count in missing_counter.items():
            allowed_count = allowance.get(text, 0)
            if count > allowed_count:
                actual_missing[text] = count - allowed_count

        assert not actual_missing, (
            f"{new_id} missing {len(actual_missing)} baseline strings; "
            f"examples: {dict(sorted(actual_missing.items())[:3])}"
        )

    # Check for unexpected extra text: anything in rendered not in baseline
    extra_counter = rendered_counter - expected_counter
    assert not extra_counter, (
        f"{new_id} renders {len(extra_counter)} unexpected strings not in baseline; "
        f"examples: {dict(sorted(extra_counter.items())[:3])}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="progress meter for the split; the marker comes off in Task 9",
)
def test_every_experiment_is_checked() -> None:
    """Once the split is done, all 25 must be covered."""
    assert len(EXTRACTED) == 25, f"only {len(EXTRACTED)}/25 extracted so far"
