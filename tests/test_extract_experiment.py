"""The extractor must pull in what a block needs, and nothing it doesn't."""
import ast

from scripts.extract_experiment import build_module, closure

SOURCE = '''\
import streamlit as st
import numpy as np

CONSTANT = {"a": 1}
OTHER = 42


def helper(x):
    return x * CONSTANT["a"]


def unrelated(x):
    return x + OTHER


def section():
    st.write(helper(2))
'''


def test_closure_pulls_transitive_dependencies() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    names = {getattr(n, "name", None) or n.targets[0].id
             for n in closure(tree, [section])}
    assert names == {"helper", "CONSTANT"}


def test_closure_excludes_unreachable_helpers() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    names = {getattr(n, "name", None) or n.targets[0].id
             for n in closure(tree, [section])}
    assert "unrelated" not in names and "OTHER" not in names


def test_build_module_emits_render_with_the_body() -> None:
    tree = ast.parse(SOURCE)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    out = build_module(SOURCE, section.body, [section], "Extracted test.")
    assert out.startswith('"""Extracted test.')
    assert "import streamlit as st" in out
    assert "def helper(x):" in out
    assert "def unrelated" not in out
    assert "def render() -> None:" in out
    assert "    st.write(helper(2))" in out
    compile(out, "<extracted>", "exec")  # must be valid Python


SOURCE_WITH_COMMENTS = '''\
import streamlit as st

# Slope controller
def helper(x):
    # scale by two, matches the UI slider
    return x * 2


def section():
    value = helper(2)
    # log it for debugging
    st.write(value)
'''


def test_build_module_preserves_comments_not_just_code() -> None:
    """ast.unparse silently drops comments; build_module must not use it."""
    tree = ast.parse(SOURCE_WITH_COMMENTS)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    out = build_module(SOURCE_WITH_COMMENTS, section.body, [section],
                        "Comments test.")
    assert "# Slope controller" in out          # leading comment above helper's def
    assert "# scale by two, matches the UI slider" in out  # interior to helper
    assert "# log it for debugging" in out      # interior to the extracted body
    compile(out, "<extracted>", "exec")  # must still be valid Python


SOURCE_WITH_ODD_TARGETS = '''\
import streamlit as st

A_LO, A_HI = 0, 100

B: dict = {"x": 1}


def section():
    st.write(A_LO, A_HI, B)
'''


def test_closure_indexes_annassign_and_tuple_targets() -> None:
    """AnnAssign and tuple-unpacking Assign targets must not be dropped."""
    tree = ast.parse(SOURCE_WITH_ODD_TARGETS)
    section = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "section")
    names = set()
    for n in closure(tree, [section]):
        if isinstance(n, ast.AnnAssign):
            names.add(n.target.id)
        elif isinstance(n, ast.Assign):
            for target in n.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Tuple):
                    names |= {elt.id for elt in target.elts}
    assert names == {"A_LO", "A_HI", "B"}
