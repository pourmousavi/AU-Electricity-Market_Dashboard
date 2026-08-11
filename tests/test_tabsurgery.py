import ast
from pathlib import Path

import pytest

from hub.tabsurgery import TabSurgeryError, select_tab

ROOT = Path(__file__).resolve().parent.parent

FIXTURE = '''
import streamlit as st
tab1, tab2, tab3 = st.tabs(["Alpha", "Beta", "Gamma"])
with tab1:
    kept_alpha = 1
with tab2:
    kept_beta = 2
with tab3:
    kept_gamma = 3
'''


def _body_of(tree: ast.Module, name: str) -> list[ast.stmt]:
    for node in ast.walk(tree):
        if (isinstance(node, ast.With) and len(node.items) == 1
                and isinstance(node.items[0].context_expr, ast.Name)
                and node.items[0].context_expr.id == name):
            return node.body
    raise AssertionError(f"no with-block for {name}")


def test_returns_selected_index() -> None:
    _, idx = select_tab(FIXTURE, "Beta")
    assert idx == 1


def test_selected_body_is_preserved() -> None:
    tree, _ = select_tab(FIXTURE, "Beta")
    assert not isinstance(_body_of(tree, "tab2")[0], ast.Pass)


def test_unselected_bodies_are_blanked() -> None:
    tree, _ = select_tab(FIXTURE, "Beta")
    for name in ("tab1", "tab3"):
        body = _body_of(tree, name)
        assert len(body) == 1 and isinstance(body[0], ast.Pass)


def test_transformed_tree_still_compiles() -> None:
    tree, _ = select_tab(FIXTURE, "Gamma")
    compile(tree, "<test>", "exec")


def test_unselected_code_does_not_execute() -> None:
    """The point of the whole exercise: blanked tabs never run."""
    tree, idx = select_tab(FIXTURE, "Gamma")
    import contextlib
    import streamlit as st

    original = st.tabs
    st.tabs = lambda labels, *a, **k: [contextlib.nullcontext()] * len(labels)
    try:
        namespace: dict = {}
        exec(compile(tree, "<test>", "exec"), namespace)
    finally:
        st.tabs = original

    assert "kept_gamma" in namespace
    assert "kept_alpha" not in namespace
    assert "kept_beta" not in namespace


def test_rejects_unknown_selector() -> None:
    with pytest.raises(TabSurgeryError, match="no tab labelled"):
        select_tab(FIXTURE, "Delta")


def test_rejects_source_without_tabs() -> None:
    with pytest.raises(TabSurgeryError, match="exactly one"):
        select_tab("x = 1\n", "Alpha")


MULTI_ITEM_FIXTURE = '''
import contextlib
import streamlit as st
tab1, tab2 = st.tabs(["Alpha", "Beta"])
with tab1, contextlib.nullcontext():
    kept_a = 1
with tab2:
    kept_b = 2
'''


def test_rejects_tab_combined_with_another_context_manager() -> None:
    """A `with tab1, other():` must be rejected, not silently skipped.

    Regression test: the original implementation only matched `with` blocks
    with exactly one item, so a tab variable combined with another context
    manager in the same `with` statement was neither blanked nor rejected —
    it silently survived untouched, contradicting the strict-failure design
    intent.
    """
    with pytest.raises(TabSurgeryError, match="tab1"):
        select_tab(MULTI_ITEM_FIXTURE, "Beta")


SHADOWED_NAME_FIXTURE = '''
import streamlit as st

tab1, tab2 = st.tabs(["Alpha", "Beta"])


def helper():
    tab1 = some_other_context_manager()
    with tab1:
        untouched = 1
    return untouched


with tab1:
    kept_alpha = 1
with tab2:
    kept_beta = 2
'''


def test_unrelated_nested_scope_with_shadowed_name_is_not_blanked() -> None:
    """A same-named local in an unrelated nested scope must not be touched.

    Regression test: the original implementation matched `with` blocks by
    variable name alone via `ast.walk` over the whole tree, with no scope
    confinement. A nested function that happens to bind a local also named
    `tab1` had its unrelated `with tab1:` block blanked to `pass`, deleting
    code that has nothing to do with tab isolation.
    """
    tree, _ = select_tab(SHADOWED_NAME_FIXTURE, "Beta")
    compile(tree, "<test>", "exec")

    func = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "helper"
    )
    inner_with = next(node for node in ast.walk(func) if isinstance(node, ast.With))
    assert not isinstance(inner_with.body[0], ast.Pass)
    assert isinstance(inner_with.body[0], ast.Assign)


@pytest.mark.parametrize(
    "filename,selector,expected_index",
    [
        ("week6_duality.py", "Strong Duality", 0),
        ("week6_duality.py", "Duality Theorems", 2),
        ("week7_ed_viu.py", "🎯 Pareto Frontier", 4),
        ("week8_pf_auction.py", "📚 Theory & Concepts", 5),
        ("week8_pf_auction.py", "🏪 Market Setup", 0),
    ],
)
def test_works_on_real_sources(filename: str, selector: str, expected_index: int) -> None:
    source = (ROOT / "sources" / filename).read_text(encoding="utf-8")
    tree, idx = select_tab(source, selector)
    assert idx == expected_index
    compile(tree, filename, "exec")
