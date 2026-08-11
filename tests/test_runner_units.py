"""Unit tests for the runner's patching primitives.

Full end-to-end rendering of all 25 experiments is Task 7.
"""
import contextlib

import pytest
import streamlit as st

from hub.catalogue import load_catalogue
from hub.runner import ExperimentRenderError, _no_page_config, _pinned_selectbox, _pinned_tabs, prepare


def test_page_config_is_noop_inside_context_and_restored_after() -> None:
    original = st.set_page_config
    with _no_page_config():
        assert st.set_page_config is not original
        st.set_page_config(page_title="ignored")  # must not raise
    assert st.set_page_config is original


def test_pinned_selectbox_returns_selector_on_first_call_only() -> None:
    original = st.sidebar.selectbox
    calls = []
    with _pinned_selectbox("Supplier Model"):
        first = st.sidebar.selectbox("Pick", ["Consumer Model", "Supplier Model"])
        calls.append(first)
    assert calls == ["Supplier Model"]
    # Bound methods are created fresh on each attribute access, so `is` would
    # compare two distinct-but-equal wrappers. `==` compares __func__/__self__,
    # which is the real question: was the genuine selectbox restored?
    assert st.sidebar.selectbox == original


def test_pinned_selectbox_rejects_absent_option() -> None:
    with pytest.raises(ExperimentRenderError, match="not among the options"):
        with _pinned_selectbox("Nonexistent"):
            st.sidebar.selectbox("Pick", ["Consumer Model"])


def test_pinned_tabs_returns_nullcontext_for_unselected() -> None:
    with _pinned_tabs(1, "Beta"):
        tabs = st.tabs(["Alpha", "Beta", "Gamma"])
    assert len(tabs) == 3
    assert isinstance(tabs[0], contextlib.nullcontext)
    assert isinstance(tabs[2], contextlib.nullcontext)
    assert not isinstance(tabs[1], contextlib.nullcontext)


def test_prepare_returns_index_for_pin_tab() -> None:
    exp = load_catalogue()["w7.pareto"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == 4


def test_prepare_returns_minus_one_for_pin_selectbox() -> None:
    exp = load_catalogue()["w2.supplier_model"]
    _, index = prepare(str(exp.source_path), exp.mode, exp.selector)
    assert index == -1
