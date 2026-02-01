"""Unit tests for transcript parser."""
import io
import pytest
from app.ingest.parser import (
    parse_transcript,
    parse_transcript_stream,
    has_valid_transcript_format,
    LINE_RE,
    Turn,
)


def test_line_re_matches_valid_line():
    assert LINE_RE.match("[00:00:00] Alex: Hello world") is not None
    assert LINE_RE.match("[01:23:45] Speaker Name: Some text here") is not None


def test_line_re_rejects_invalid():
    assert LINE_RE.match("plain text") is None
    assert LINE_RE.match("[00:00:00] No colon") is None
    assert LINE_RE.match("[00:00] Alex: Short timestamp") is None


def test_parse_transcript_valid():
    text = "[00:00:00] Alex: Hello.\n[00:00:05] Sam: Hi there."
    turns = parse_transcript(text)
    assert len(turns) == 2
    assert turns[0].timestamp == "00:00:00"
    assert turns[0].speaker == "Alex"
    assert turns[0].text == "Hello."
    assert turns[1].timestamp == "00:00:05"
    assert turns[1].speaker == "Sam"
    assert turns[1].text == "Hi there."


def test_parse_transcript_continuation_line():
    text = "[00:00:00] Alex: Line one\n  continuation here"
    turns = parse_transcript(text)
    assert len(turns) == 1
    assert "Line one" in turns[0].text
    assert "continuation" in turns[0].text


def test_parse_transcript_empty():
    assert parse_transcript("") == []
    assert parse_transcript("   \n\n  ") == []


def test_has_valid_transcript_format_true():
    assert has_valid_transcript_format("[00:00:00] Alex: Hello") is True
    assert has_valid_transcript_format("junk\n[00:00:00] A: x\nmore") is True


def test_has_valid_transcript_format_false():
    assert has_valid_transcript_format("") is False
    assert has_valid_transcript_format("no timestamp here") is False
    assert has_valid_transcript_format("  \n  ") is False
