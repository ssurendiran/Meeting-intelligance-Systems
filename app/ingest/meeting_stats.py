"""
Meeting-level stats from transcript turns: total duration, per-speaker turn/word counts.
Used at ingest to store metadata so RAG can answer "total duration" and "who talked the most".
"""
import json
import os
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.ingest.parser import Turn


def timestamp_to_seconds(ts: str) -> int:
    """Convert HH:MM:SS (or [HH:]MM:SS) to total seconds.
    Why available: Used by RAG for time-filtered retrieval and by meeting stats for duration calculations."""
    parts = (ts or "0:0:0").strip().split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    elif len(parts) == 1:
        parts = ["0", "0"] + parts
    try:
        h, m, s = int(parts[-3]), int(parts[-2]), int(parts[-1])
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        return 0


def _timestamp_to_seconds(ts: str) -> int:
    """Alias for timestamp_to_seconds (internal use). Used by compute_meeting_stats."""
    return timestamp_to_seconds(ts)


def _seconds_to_display(seconds: int) -> str:
    """Format seconds as HH:MM:SS or M:SS. Used for human-readable duration in metadata and summary."""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def compute_meeting_stats(turns: List[Turn]) -> Dict[str, Any]:
    """Compute meeting-level stats: total duration, per-speaker turn/word counts and speaking duration. Speaking duration per turn = time until next turn; summed per speaker. Sorted by participation (most first).
    Why available: Stored at ingest so RAG can answer questions about total duration and who talked most/least."""
    if not turns:
        return {
            "total_duration_seconds": 0,
            "total_duration_display": "0:00",
            "first_timestamp": "00:00:00",
            "last_timestamp": "00:00:00",
            "speaker_stats": [],
        }

    # Order turns by timestamp then line_no for duration calculation
    turns_ordered = sorted(
        turns,
        key=lambda t: (_timestamp_to_seconds(t.timestamp), t.line_no),
    )
    seconds_list = [_timestamp_to_seconds(t.timestamp) for t in turns_ordered]
    start_sec = min(seconds_list)
    end_sec = max(seconds_list)
    total_duration_seconds = max(0, end_sec - start_sec)

    turn_count_by_speaker: Dict[str, int] = defaultdict(int)
    word_count_by_speaker: Dict[str, int] = defaultdict(int)
    duration_seconds_by_speaker: Dict[str, int] = defaultdict(int)

    for i, t in enumerate(turns_ordered):
        name = (t.speaker or "Unknown").strip()
        turn_count_by_speaker[name] += 1
        word_count_by_speaker[name] += len((t.text or "").split())
        ts_sec = _timestamp_to_seconds(t.timestamp)
        # This turn's "holding the floor" duration: until next turn or end of meeting
        if i + 1 < len(turns_ordered):
            next_sec = _timestamp_to_seconds(turns_ordered[i + 1].timestamp)
            duration_seconds_by_speaker[name] += max(0, next_sec - ts_sec)
        else:
            duration_seconds_by_speaker[name] += max(0, end_sec - ts_sec)

    speaker_stats = [
        {
            "speaker": name,
            "turn_count": turn_count_by_speaker[name],
            "word_count": word_count_by_speaker[name],
            "duration_seconds": duration_seconds_by_speaker[name],
            "duration_display": _seconds_to_display(duration_seconds_by_speaker[name]),
        }
        for name in sorted(turn_count_by_speaker.keys())
    ]
    # Sort by duration (most spoke first), then turn_count, so "who talked the most/least" is clear
    speaker_stats.sort(
        key=lambda x: (x["duration_seconds"], x["turn_count"], x["word_count"]),
        reverse=True,
    )

    first_timestamp = turns_ordered[0].timestamp if turns_ordered else "00:00:00"
    last_timestamp = turns_ordered[-1].timestamp if turns_ordered else "00:00:00"
    return {
        "total_duration_seconds": total_duration_seconds,
        "total_duration_display": _seconds_to_display(total_duration_seconds),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "speaker_stats": speaker_stats,
    }


def format_meeting_overview(metadata: Dict[str, Any]) -> str:
    """Format meeting metadata for RAG context: total duration, who talked most/least, per-speaker duration.
    Why available: Prepended to RAG context so the LLM can answer duration and participation questions from stored stats."""
    if not metadata:
        return ""
    parts = ["Meeting overview (use for questions about duration or who spoke most/least):"]
    parts.append(f"Total call duration: {metadata.get('total_duration_display', '0:00')}")
    stats = metadata.get("speaker_stats") or []
    if stats:
        most = stats[0]["speaker"]
        least = stats[-1]["speaker"] if len(stats) > 1 else most
        parts.append(f"Who talked the most: {most}. Who talked the least: {least}.")
        parts.append(
            "Per-speaker duration (speaking time): "
            + "; ".join(
                f"{s['speaker']} ({s.get('duration_display', '0:00')}, {s['turn_count']} turns)"
                for s in stats
            )
        )
    return "\n".join(parts)


def _metadata_path(meeting_id: str, data_root: str) -> str:
    """Path to meeting metadata JSON file. Used by save_meeting_metadata and load_meeting_metadata."""
    base = os.path.join(data_root, "meeting_metadata")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{meeting_id}.json")


def save_meeting_metadata(meeting_id: str, metadata: Dict[str, Any], data_root: str) -> None:
    """Persist meeting metadata to data/meeting_metadata/{meeting_id}.json.
    Why available: Called after ingest so RAG and summary can load duration and speaker stats later."""
    path = _metadata_path(meeting_id, data_root)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def load_meeting_metadata(meeting_id: str, data_root: str) -> Optional[Dict[str, Any]]:
    """Load meeting metadata from data/meeting_metadata/{meeting_id}.json if present.
    Why available: Used by RAG context builder and summary to include duration and speaker participation in context."""
    path = _metadata_path(meeting_id, data_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
