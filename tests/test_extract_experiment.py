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
