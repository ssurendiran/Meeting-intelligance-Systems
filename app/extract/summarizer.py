import json
from typing import Dict, Any, Set, Optional

from app.core.config import settings
from app.core.openai_client import get_openai_client
from app.prompts.loader import get_system_prompt, get_user_prompt
from app.rag.context import pack_context
from app.rag.retriever import retrieve
from app.ingest.meeting_stats import load_meeting_metadata, format_meeting_overview, timestamp_to_seconds


def allowed_sources(retrieved) -> Set[str]:
    """Return the set of allowed evidence keys (file:line_start-line_end) from retrieved chunks.
    Why available: Used to filter summary items so only evidence from retrieved context is kept (no hallucinated citations)."""
    allowed = set()
    for r in retrieved:
        f, a, b = r.get("file"), r.get("line_start"), r.get("line_end")
        if f and isinstance(a, int) and isinstance(b, int):
            allowed.add(f"{f}:{a}-{b}")
    return allowed


def filter_evidence(data: Dict[str, Any], allowed: Set[str]) -> Dict[str, Any]:
    """Filter summary data to only include decisions, action_items, and risks whose evidence key (file:line_start-line_end) is in the allowed set from retrieved chunks. Other fields (key_discussions, planning, meeting_about, outcome, mom) are passed through.
    Why available: Ensures summary items are grounded in retrieved context only (no hallucinated evidence)."""
    def keep(items):
        """Return only list items whose 'evidence' key is in the allowed set. Used by filter_evidence to filter decisions, action_items, risks."""
        out = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            ev = it.get("evidence")
            if isinstance(ev, str) and ev in allowed:
                out.append(it)
        return out

    out = {
        "decisions": keep(data.get("decisions", [])),
        "action_items": keep(data.get("action_items", [])),
        "risks_or_open_questions": keep(data.get("risks_or_open_questions", [])),
    }
    # Pass through MOM-style fields (no evidence filter)
    for key in ("key_discussions", "planning"):
        val = data.get(key)
        out[key] = [str(x) for x in (val or []) if x] if isinstance(val, list) else []
    for key in ("meeting_about", "outcome", "mom"):
        val = data.get(key)
        out[key] = (val or "").strip() or None if isinstance(val, str) else None
    return out


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    """Parse the LLM output as JSON. If parsing fails or output is not JSON, tries to extract the first {...} block; otherwise returns an empty summary schema (None/empty lists).
    Why available: Makes summary extraction robust to malformed or mixed LLM output."""
    raw = (raw or "").strip()
    if not raw:
        return {
            "meeting_about": None,
            "key_discussions": [],
            "planning": [],
            "outcome": None,
            "mom": None,
            "decisions": [],
            "action_items": [],
            "risks_or_open_questions": [],
        }
    try:
        return json.loads(raw)
    except Exception:
        # fallback: try to extract the first {...} block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                pass
    return {
        "meeting_about": None,
        "key_discussions": [],
        "planning": [],
        "outcome": None,
        "mom": None,
        "decisions": [],
        "action_items": [],
        "risks_or_open_questions": [],
    }


def summarize(meeting_id: str, data_root: Optional[str] = None) -> tuple[Dict[str, Any], Dict[str, int]]:
    """Extract meeting summary (about, discussions, planning, outcome, MOM) from retrieved context via LLM.
    Returns (data, usage). If data_root is provided, loads meeting metadata and adds call_duration and speaker_participation.
    Why available: Powers the /summary API so users get structured summaries without reading the full transcript."""
    meeting_meta = load_meeting_metadata(meeting_id, data_root) if data_root else None

    retrieved = retrieve(
        meeting_id=meeting_id,
        question="decisions action items owners due dates risks open questions",
        top_k=12,
    )

    # Derive start/end time from chunks when metadata does not have them (e.g. older ingests)
    meeting_meta = meeting_meta or {}
    if retrieved:
        time_starts = [r["time_start"] for r in retrieved if r.get("time_start")]
        time_ends = [r["time_end"] for r in retrieved if r.get("time_end")]
        if time_starts and not meeting_meta.get("first_timestamp"):
            meeting_meta["first_timestamp"] = min(time_starts, key=lambda t: timestamp_to_seconds(t))
        if time_ends and not meeting_meta.get("last_timestamp"):
            meeting_meta["last_timestamp"] = max(time_ends, key=lambda t: timestamp_to_seconds(t))

    # If nothing retrieved, return empty schema (still add duration/speaker if we have metadata)
    if not retrieved:
        out = {
            "meeting_about": None,
            "key_discussions": [],
            "planning": [],
            "outcome": None,
            "mom": None,
            "decisions": [],
            "action_items": [],
            "risks_or_open_questions": [],
        }
        _merge_meeting_meta(out, meeting_meta)
        return out, {"prompt_tokens": 0, "completion_tokens": 0}

    context = pack_context(retrieved, max_chunks=min(10, len(retrieved)))
    if meeting_meta:
        overview = format_meeting_overview(meeting_meta)
        if overview:
            context = overview + "\n\n---\n\n" + context
    allowed_list = sorted(list(allowed_sources(retrieved)))
    allowed_set = set(allowed_list)

    oc = get_openai_client()

    system_prompt = get_system_prompt("extract_summary")
    user_prompt = get_user_prompt("extract_summary")
    user_msg = user_prompt.replace("<<CONTEXT>>", context).replace(
        "<<ALLOWED_EVIDENCE>>", "\n".join(allowed_list)
    )

    resp = oc.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    u = getattr(resp, "usage", None)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if u is not None:
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0, "completion_tokens": getattr(u, "completion_tokens", 0) or 0}

    raw = resp.choices[0].message.content or ""
    data = _safe_json_loads(raw)
    data = filter_evidence(data, allowed_set)
    _merge_meeting_meta(data, meeting_meta)
    return data, usage


def _merge_meeting_meta(data: Dict[str, Any], meeting_meta: Optional[Dict[str, Any]]) -> None:
    """Merge start_time, end_time, call_duration and speaker_participation from meeting_meta into data (in-place).
    Why available: Enriches summary response with stored meeting stats (duration, who spoke most/least)."""
    if not meeting_meta:
        return
    data["start_time"] = meeting_meta.get("first_timestamp")
    data["end_time"] = meeting_meta.get("last_timestamp")
    data["call_duration"] = meeting_meta.get("total_duration_display")
    stats = meeting_meta.get("speaker_stats") or []
    data["speaker_participation"] = [
        {
            "speaker": s["speaker"],
            "duration_display": s.get("duration_display", "0:00"),
            "turn_count": s["turn_count"],
            "word_count": s["word_count"],
        }
        for s in stats
    ]
