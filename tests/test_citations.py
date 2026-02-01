"""Unit tests for citation guardrails."""
import pytest
from app.guardrails.citations import (
    allowed_ranges,
    citation_overlaps_range,
    normalize_and_filter_citations,
    require_citations_or_refuse,
)
from app.models.schemas import Citation


def test_allowed_ranges():
    retrieved = [
        {"file": "a.txt", "line_start": 1, "line_end": 10},
        {"file": "b.txt", "line_start": 5, "line_end": 15},
    ]
    out = allowed_ranges(retrieved)
    assert out == {("a.txt", 1, 10), ("b.txt", 5, 15)}


def test_allowed_ranges_skips_invalid():
    retrieved = [
        {"file": "a.txt", "line_start": 1, "line_end": 10},
        {"file": None, "line_start": 1, "line_end": 2},
        {"file": "b.txt"},
    ]
    out = allowed_ranges(retrieved)
    assert out == {("a.txt", 1, 10)}


def test_citation_overlaps_range():
    allowed = {("a.txt", 1, 10), ("b.txt", 5, 15)}
    assert citation_overlaps_range("a.txt", 2, 5, allowed) is True
    assert citation_overlaps_range("a.txt", 8, 12, allowed) is True  # overlap
    assert citation_overlaps_range("a.txt", 11, 20, allowed) is False
    assert citation_overlaps_range("c.txt", 1, 5, allowed) is False


def test_normalize_and_filter_citations():
    allowed = {("a.txt", 1, 10)}
    citations = [
        Citation(file="a.txt", line_start=3, line_end=7),
        Citation(file="b.txt", line_start=1, line_end=2),
    ]
    out = normalize_and_filter_citations(citations, allowed)
    assert len(out) == 1
    assert out[0].file == "a.txt"
    assert out[0].line_start == 3
    assert out[0].line_end == 7


def test_require_citations_or_refuse_with_citations():
    assert require_citations_or_refuse("The answer is X.", [Citation(file="a", line_start=1, line_end=2)]) == "The answer is X."


def test_require_citations_or_refuse_no_citations():
    assert require_citations_or_refuse("Something", []) == "Not found in transcript."
