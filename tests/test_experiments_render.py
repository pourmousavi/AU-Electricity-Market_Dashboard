"""Every experiment must render without raising.

This is the check that catches a vendored dashboard being restructured
upstream. Run it after every scripts/sync_sources.py.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hub.catalogue import load_catalogue

ROOT = Path(__file__).resolve().parent.parent
ALL_IDS = sorted(load_catalogue())


def _harness(exp_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from hub.catalogue import load_catalogue\n"
        "from hub.runner import render_experiment\n"
        f"render_experiment(load_catalogue()[{exp_id!r}])\n"
    )


def test_catalogue_has_expected_size() -> None:
    assert len(ALL_IDS) == 25


@pytest.mark.parametrize("exp_id", ALL_IDS)
def test_experiment_renders_without_exception(exp_id: str) -> None:
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    assert not app.exception, (
        f"{exp_id} raised: "
        + "; ".join(e.message for e in app.exception)
    )


@pytest.mark.parametrize("exp_id", ALL_IDS)
def test_experiment_produces_output(exp_id: str) -> None:
    """A silent success is a failure — every experiment must render something."""
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    produced = len(app.markdown) + len(app.header) + len(app.subheader) + len(app.title)
    assert produced > 0, f"{exp_id} rendered no text output at all"
