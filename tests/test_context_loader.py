import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import context_loader


def test_keywords_strips_stop_words():
    kws = context_loader._keywords("what is the best way to summarize this article")
    stop_words = context_loader.STOP_WORDS
    for kw in kws:
        assert kw not in stop_words, f"stop word leaked into keywords: {kw}"


def test_keywords_returns_meaningful_words():
    kws = context_loader._keywords("summarize the quarterly revenue report for finance")
    assert "summarize" in kws
    assert "quarterly" in kws
    assert "revenue" in kws
    assert "report" in kws
    assert "finance" in kws


def test_get_context_returns_string():
    result = context_loader.get_context("write a python function to sort a list")
    assert isinstance(result, str)


def test_get_context_empty_input_returns_string():
    result = context_loader.get_context("")
    assert isinstance(result, str)
