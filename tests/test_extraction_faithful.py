"""Each extracted module must render what its bundled original rendered.

Tasks add a line to EXTRACTED as they extract. An experiment that is not in
this map yet is simply not checked -- the map grows to 25 by the end of the
split, and test_every_experiment_is_checked then locks it.
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
BASELINE = json.loads((ROOT / "tests" / "baseline_render.json").read_text())

# new id -> old id. One line added per extracted experiment.
EXTRACTED: dict[str, str] = {}

# Text the extraction deliberately drops: the vendored sidebar branding of
# weeks 2, 3 and 4. Any other missing text is a defect.
ALLOWED_REMOVALS = {
    "⚡ Electricity Market Dashboard",
    "📈 3D Optimization Dashboard",
    "---",
    "### Course Information",
    "**Electricity Market and Power Systems Operation**",
    "**ELEC ENG 4087/7087**",
    "**Course Coordinator & Creator:**",
    "Ali Pourmousavi Kani",
    "**Version:** 2.0",
    "**Version:** 1.0 - Market Power & Economics",
    "**Version:** 2.0 - 3D Nonlinear Optimization",
}


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
    rendered = set()
    for kind in ("title", "header", "subheader", "markdown", "info", "warning",
                 "error", "success", "caption", "code", "text"):
        for element in getattr(app, kind, []):
            value = getattr(element, "value", None)
            if isinstance(value, str):
                rendered.add(value)

    expected = set(BASELINE[EXTRACTED[new_id]]["text"])
    missing = {t for t in expected - rendered if t.strip() not in ALLOWED_REMOVALS}
    assert not missing, (
        f"{new_id} no longer renders {len(missing)} baseline strings, e.g. "
        + repr(sorted(missing)[:3])
    )


@pytest.mark.xfail(
    strict=True,
    reason="progress meter for the split; the marker comes off in Task 9",
)
def test_every_experiment_is_checked() -> None:
    """Once the split is done, all 25 must be covered."""
    assert len(EXTRACTED) == 25, f"only {len(EXTRACTED)}/25 extracted so far"
