"""Every experiment must render without raising.

This is the check that catches an experiment module being broken -- by an
edit here, or by a dependency upgrade underneath it.
"""
import importlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hub.catalogue import load_catalogue

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = load_catalogue()
ALL_IDS = sorted(CATALOGUE)


def _harness(exp_id: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import importlib\n"
        f"module = importlib.import_module('experiments.{exp_id}')\n"
        "module.render()\n"
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


# --- Cross-experiment isolation -------------------------------------------
#
# The two tests above only catch "an experiment crashed" or "an experiment
# rendered literally nothing". Neither one catches the more likely failure
# mode of the fourteen experiments carved out of a shared tabbed dashboard:
# the wrong sibling's body being wired up, or a shared experiments/_kit page
# rendering a sibling's content alongside (or instead of) the experiment's
# own. A parametrize loop over 25 independent `AppTest` runs has no way to
# notice that on its own — each run only sees one experiment's output, with
# nothing to compare it to.
#
# This test closes that gap by asserting, per tab-derived experiment, that a
# short marker string unique to each SIBLING in the same STATE_GROUP is
# absent from the rendered output, and (with one documented exception) that
# the experiment's OWN marker is present.
#
# The markers below are short excerpts carried over verbatim from the
# bundled originals (sources/week6_duality.py, sources/week7_ed_viu.py and
# sources/week8_pf_auction.py), where each occurred only within that one
# tab's body. A failure here means either the extraction wired up the wrong
# body, or a _kit page started rendering content it should not — in either
# case this test failing is doing its job.
TAB_MARKERS: dict[str, str] = {
    # experiments/_kit/duality.py — was week6_duality.py tab1/tab2/tab3,
    # unconditional (no session_state gating), each subheader unique.
    "strong_duality": "When does strong duality hold?",
    "weak_duality": "Cases Where Strong Duality Fails",
    "duality_theorems": "Fundamental Duality Theorems",
    # experiments/_kit/dispatch.py — was week7_ed_viu.py tab1..tab5. tab1's
    # header is unconditional; tab2/tab3's headers are printed before their
    # session_state gate, so they render regardless of solve state. tab4's
    # header is unique. The Pareto frontier is the exception: its gate check
    # and `return` happen BEFORE any markdown/header is emitted, so there is
    # no header to use — the marker is the `st.info(...)` gate message
    # itself, which is what actually renders in a fresh AppTest run.
    "dispatch_generator_setup": "🏭 Generator Parameters",
    "dispatch_comparison": "📊 Comparison Results",
    "dispatch_detailed_analysis": "🔍 Detailed Analysis",
    "dispatch_individual_generators": "🏭 Individual Generator Analysis",
    "dispatch_pareto_frontier": "Solve ED-5 first to see Pareto frontier analysis.",
    # experiments/_kit/dc_network.py — was week8_pf_auction.py tab1..tab6.
    # Every one of these headers is printed before its function's
    # session_state gate (unlike week7's pareto tab), so all six own-markers
    # are present even though several render almost nothing else.
    "auction_market_setup": "🏪 Market Setup",
    "auction_network_topology": "🔌 Network Topology",
    "auction_market_results": "📈 Market Results",
    "dc_opf_results": "⚡ DC OPF Results",
    "auction_vs_dc_opf": "🔋 Only Market vs DC OPF Comparison",
    "power_flow_theory": "📚 Theory and Concepts",
}

# The tab-derived experiments are exactly the ones that share a _kit page,
# and those are exactly the ones declaring a STATE_GROUP.
TAB_IDS = sorted(
    exp_id for exp_id in CATALOGUE
    if hasattr(importlib.import_module(f"experiments.{exp_id}"), "STATE_GROUP")
)

# Sanity check that the table above matches the set of grouped experiments —
# fails loudly (at collection time) rather than silently under-testing if the
# two ever drift apart.
assert set(TAB_MARKERS) == set(TAB_IDS), (
    "TAB_MARKERS is out of sync with the experiments declaring a STATE_GROUP: "
    f"missing={set(TAB_IDS) - set(TAB_MARKERS)!r} "
    f"extra={set(TAB_MARKERS) - set(TAB_IDS)!r}"
)

_SIBLINGS_BY_GROUP: dict[str, list[str]] = {}
_GROUP_OF: dict[str, str] = {}
for _exp_id in TAB_IDS:
    _group = importlib.import_module(f"experiments.{_exp_id}").STATE_GROUP
    _GROUP_OF[_exp_id] = _group
    _SIBLINGS_BY_GROUP.setdefault(_group, []).append(_exp_id)


def _rendered_text(app) -> str:
    """All text an experiment actually put on the page, in one string."""
    parts = []
    for collection in (app.markdown, app.header, app.subheader, app.title, app.info):
        parts.extend(element.value for element in collection)
    return "\n".join(parts)


@pytest.mark.parametrize("exp_id", TAB_IDS)
def test_only_the_selected_experiment_renders(exp_id: str) -> None:
    """A tab-derived experiment renders its own body and none of its siblings'."""
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    text = _rendered_text(app)

    if exp_id != "dispatch_pareto_frontier":
        own_marker = TAB_MARKERS[exp_id]
        assert own_marker in text, (
            f"{exp_id}: own marker not found in rendered output — {own_marker!r}"
        )
    # dispatch_pareto_frontier gate-checks and returns before emitting any
    # header of its own — see the comment on TAB_MARKERS above — so there is
    # no "own content" to assert present here. The sibling-absence checks
    # below still fully apply to it.

    for sibling_id in _SIBLINGS_BY_GROUP[_GROUP_OF[exp_id]]:
        if sibling_id == exp_id:
            continue
        sibling_marker = TAB_MARKERS[sibling_id]
        assert sibling_marker not in text, (
            f"{exp_id}: sibling {sibling_id}'s marker leaked into the "
            f"rendered output — {sibling_marker!r}. The extraction likely "
            "wired up the wrong body."
        )
