"""Every experiment must render without raising.

This is the check that catches a vendored dashboard being restructured
upstream. Run it after every scripts/sync_sources.py.
"""
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


# --- Cross-tab isolation --------------------------------------------------
#
# The two tests above only catch "isolation broke and something crashed" or
# "isolation broke and rendered literally nothing". Neither one catches the
# more likely failure mode of a `pin_tab` experiment: tabsurgery (or the
# `st.tabs` pinning shim) silently selecting the WRONG sibling tab, or
# blanking the right one and leaving the wrong one live. A parametrize loop
# over 25 independent `AppTest` runs has no way to notice that on its own —
# each run only sees one experiment's output, with nothing to compare it to.
#
# This test closes that gap by asserting, per pin_tab experiment, that a
# short marker string unique to each SIBLING tab in the same source file is
# absent from the rendered output, and (with one documented exception) that
# the experiment's OWN marker is present. If tabsurgery ever selects the
# wrong tab, a sibling's marker leaks into the output and this test catches
# it even in cases (like w7.pareto) where the correctly-selected tab itself
# renders almost nothing.
#
# The markers below are short excerpts copied verbatim from
# sources/week6_duality.py, sources/week7_ed_viu.py and
# sources/week8_pf_auction.py. Each was verified with `grep -nF <marker>
# sources/<file>` to occur only within that one tab's body (occurrences in
# the file's `st.tabs([...])` label list don't count — the pinning shim in
# hub.runner only ever passes a single-element label list to the real
# `st.tabs`, so the other labels are never rendered as text and can't
# collide). A failure here means either the isolation layer broke, or the
# upstream vendored dashboard was restructured (e.g. by
# scripts/sync_sources.py) and these markers need to be re-picked from the
# new source — in the latter case this test failing is doing its job.
PIN_TAB_MARKERS: dict[str, str] = {
    # sources/week6_duality.py — tab1/tab2/tab3, unconditional (no
    # session_state gating), each subheader is unique file-wide.
    "w6.strong_duality": "When does strong duality hold?",
    "w6.weak_duality": "Cases Where Strong Duality Fails",
    "w6.duality_theorems": "Fundamental Duality Theorems",
    # sources/week7_ed_viu.py — tab1..tab5. tab1's header is unconditional;
    # tab2/tab3's headers are printed before their session_state gate, so
    # they render regardless of solve state. tab4's header is unique
    # file-wide. tab5 (render_pareto_frontier) is the exception: its gate
    # check and `return` happen BEFORE any markdown/header is emitted, so
    # there is no header to use — the marker is the `st.info(...)` gate
    # message itself, which is what actually renders in a fresh AppTest run.
    "w7.generator_setup": "🏭 Generator Parameters",
    "w7.comparison_results": "📊 Comparison Results",
    "w7.detailed_analysis": "🔍 Detailed Analysis",
    "w7.individual_generators": "🏭 Individual Generator Analysis",
    "w7.pareto": "Solve ED-5 first to see Pareto frontier analysis.",
    # sources/week8_pf_auction.py — tab1..tab6. Every one of these headers
    # is printed before its function's session_state gate (unlike
    # week7's pareto tab), so all six own-markers are present even though
    # several tabs render almost nothing else.
    "w8.market_setup": "🏪 Market Setup",
    "w8.network_topology": "🔌 Network Topology",
    "w8.market_results": "📈 Market Results",
    "w8.dc_opf_results": "⚡ DC OPF Results",
    "w8.market_vs_opf": "🔋 Only Market vs DC OPF Comparison",
    "w8.theory": "📚 Theory and Concepts",
}

PIN_TAB_IDS = sorted(
    exp_id for exp_id, exp in CATALOGUE.items() if exp.mode == "pin_tab"
)

# Sanity check that the table above matches the catalogue's pin_tab set —
# fails loudly (at collection time) rather than silently under-testing if
# the two ever drift apart.
assert set(PIN_TAB_MARKERS) == set(PIN_TAB_IDS), (
    "PIN_TAB_MARKERS is out of sync with catalogue.yaml's pin_tab experiments: "
    f"missing={set(PIN_TAB_IDS) - set(PIN_TAB_MARKERS)!r} "
    f"extra={set(PIN_TAB_MARKERS) - set(PIN_TAB_IDS)!r}"
)

_SIBLINGS_BY_SOURCE: dict[str, list[str]] = {}
for _exp_id in PIN_TAB_IDS:
    _SIBLINGS_BY_SOURCE.setdefault(CATALOGUE[_exp_id].source_key, []).append(_exp_id)


def _rendered_text(app) -> str:
    """All text an experiment actually put on the page, in one string."""
    parts = []
    for collection in (app.markdown, app.header, app.subheader, app.title, app.info):
        parts.extend(element.value for element in collection)
    return "\n".join(parts)


@pytest.mark.parametrize("exp_id", PIN_TAB_IDS)
def test_only_the_selected_tab_renders(exp_id: str) -> None:
    """A pin_tab experiment must render its own tab and none of its siblings'."""
    exp = CATALOGUE[exp_id]
    app = AppTest.from_string(_harness(exp_id), default_timeout=180).run()
    text = _rendered_text(app)

    if exp_id != "w7.pareto":
        own_marker = PIN_TAB_MARKERS[exp_id]
        assert own_marker in text, (
            f"{exp_id}: own marker not found in rendered output — {own_marker!r}"
        )
    # w7.pareto's render_pareto_frontier() gate-checks and returns before
    # emitting any header of its own — see the comment on PIN_TAB_MARKERS
    # above — so there is no "own content" to assert present here. The
    # sibling-absence checks below still fully apply to it.

    for sibling_id in _SIBLINGS_BY_SOURCE[exp.source_key]:
        if sibling_id == exp_id:
            continue
        sibling_marker = PIN_TAB_MARKERS[sibling_id]
        assert sibling_marker not in text, (
            f"{exp_id}: sibling {sibling_id}'s marker leaked into the "
            f"rendered output — {sibling_marker!r}. Isolation likely "
            "selected the wrong tab."
        )
