"""Unit tests for timestamp parsing (main and meeting_stats)."""
import pytest
from app.main import _parse_timestamps_from_question
from app.ingest.meeting_stats import timestamp_to_seconds


def test_parse_timestamps_bracket():
    assert _parse_timestamps_from_question("What happened at [00:12:46]?") == ["00:12:46"]
    assert _parse_timestamps_from_question("[00:00:00] and [01:00:00]") == ["00:00:00", "01:00:00"]


def test_parse_timestamps_standalone():
    assert _parse_timestamps_from_question("at 00:13:00 who was talking?") == ["00:13:00"]
    assert _parse_timestamps_from_question("at 00:00:00") == ["00:00:00"]


def test_parse_timestamps_dedup():
    assert _parse_timestamps_from_question("[00:12:46] at 00:12:46") == ["00:12:46"]


def test_parse_timestamps_empty():
    assert _parse_timestamps_from_question("") == []
    assert _parse_timestamps_from_question("no timestamp here") == []
    assert _parse_timestamps_from_question("   ") == []


def test_timestamp_to_seconds():
    assert timestamp_to_seconds("00:00:00") == 0
    assert timestamp_to_seconds("00:01:00") == 60
    assert timestamp_to_seconds("01:00:00") == 3600
    assert timestamp_to_seconds("00:12:46") == 12 * 60 + 46
    assert timestamp_to_seconds("1:30") == 90  # MM:SS
    assert timestamp_to_seconds("30") == 30   # SS only
