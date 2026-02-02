# Main (Home) page content for Meeting Intelligence Assistant.
import html
import re
import time
import json
import base64
import os
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

# Transcript format: [HH:MM:SS] Speaker: text (must have at least one such line)
TRANSCRIPT_LINE_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*[^:]{1,60}:\s*.+")
INGEST_MAX_BYTES = 1 * 1024 * 1024  # 1 MB max


def _topic_to_filename(topic: str) -> str:
    """Sanitize topic for use as download filename: alphanumeric + underscores, max 80 chars, .txt."""
    if not (topic or "").strip():
        return "sample_transcript.txt"
    s = re.sub(r"[^\w\s-]", "", (topic or "").strip())
    s = re.sub(r"[-\s]+", "_", s).strip("_")[:80] or "sample_transcript"
    return f"{s}.txt" if not s.lower().endswith(".txt") else s


API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def _status_badge(label: str, color: str) -> None:
    """Render a colored status badge (red = loading, green = done)."""
    st.markdown(
        f'<div style="background:{color};color:white;padding:6px 14px;border-radius:6px;'
        'display:inline-block;font-weight:500;">{}</div>'.format(label),
        unsafe_allow_html=True,
    )


def _gen_btn_red_loading() -> None:
    """Render the Generate sample transcript button as red with moving/pulse animation (loading state)."""
    st.markdown(
        """
        <style>
        @keyframes gen-pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.5); }
            50% { opacity: 0.85; box-shadow: 0 0 0 8px rgba(220, 53, 69, 0); }
        }
        .gen-btn-loading {
            background: #dc3545;
            color: white;
            padding: 8px 20px;
            border-radius: 6px;
            display: inline-block;
            font-weight: 500;
            animation: gen-pulse 1.2s ease-in-out infinite;
            pointer-events: none;
        }
        </style>
        <div class="gen-btn-loading">Generate sample transcript</div>
        """,
        unsafe_allow_html=True,
    )


def _gen_btn_green_done() -> None:
    """Render the Generate sample transcript area as green (done state)."""
    st.markdown(
        '<div style="background:#28a745;color:white;padding:8px 20px;border-radius:6px;'
        'display:inline-block;font-weight:500;">✓ Sample transcript ready</div>',
        unsafe_allow_html=True,
    )


def _ingest_btn_red_loading() -> None:
    """Render the Ingest button as red with pulse animation (loading state)."""
    st.markdown(
        """
        <style>
        @keyframes ingest-pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.5); }
            50% { opacity: 0.85; box-shadow: 0 0 0 8px rgba(220, 53, 69, 0); }
        }
        .ingest-btn-loading {
            background: #dc3545;
            color: white;
            padding: 8px 20px;
            border-radius: 6px;
            display: inline-block;
            font-weight: 500;
            animation: ingest-pulse 1.2s ease-in-out infinite;
            pointer-events: none;
        }
        </style>
        <div class="ingest-btn-loading">📥 Ingest</div>
        """,
        unsafe_allow_html=True,
    )


def _ingest_btn_green_done() -> None:
    """Render the Ingest area as green (done state)."""
    st.markdown(
        '<div style="background:#28a745;color:white;padding:8px 20px;border-radius:6px;'
        'display:inline-block;font-weight:500;">✓ Ingest complete</div>',
        unsafe_allow_html=True,
    )


def _extract_btn_red_loading() -> None:
    """Render the Extract Summary button as red with pulse animation (loading state)."""
    st.markdown(
        """
        <style>
        @keyframes extract-pulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.5); }
            50% { opacity: 0.85; box-shadow: 0 0 0 8px rgba(220, 53, 69, 0); }
        }
        .extract-btn-loading {
            background: #dc3545;
            color: white;
            padding: 8px 20px;
            border-radius: 6px;
            display: inline-block;
            font-weight: 500;
            animation: extract-pulse 1.2s ease-in-out infinite;
            pointer-events: none;
        }
        </style>
        <div class="extract-btn-loading">🧾 Extract Summary</div>
        """,
        unsafe_allow_html=True,
    )


def _extract_btn_green_done() -> None:
    """Render the Extract Summary area as green (done state)."""
    st.markdown(
        '<div style="background:#28a745;color:white;padding:8px 20px;border-radius:6px;'
        'display:inline-block;font-weight:500;">✓ Summary ready</div>',
        unsafe_allow_html=True,
    )


def post_json(path: str, payload: dict, stream: bool = False):
    """POST JSON payload to API path."""
    url = f"{API_BASE}{path}"
    return requests.post(url, json=payload, timeout=120, stream=stream)


def pretty_json(obj):
    """Return a pretty-printed JSON string for display."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def summary_to_natural_language(data: dict) -> str:
    """Convert summary JSON into readable natural language: duration, speakers, about, discussions, planning, outcome, MOM."""
    if not data:
        return "No summary available."
    parts = []
    # Start time, end time, call duration and speaker participation
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    call_duration = data.get("call_duration")
    speaker_part = data.get("speaker_participation") or []
    if start_time or end_time or call_duration or speaker_part:
        parts.append("**Meeting time & speaker participation**\n\n")
        parts.append(f"Start time: **{start_time or '—'}** · End time: **{end_time or '—'}**\n\n")
        if call_duration:
            parts.append(f"Total duration: {call_duration}\n\n")
        if speaker_part:
            most = speaker_part[0].get("speaker", "") if speaker_part else ""
            least = speaker_part[-1].get("speaker", "") if len(speaker_part) > 1 else most
            parts.append(f"Who talked the most: **{most}**. Who talked the least: **{least}**.\n\n")
            parts.append("Per-speaker duration (speaking time):\n")
            for s in speaker_part:
                name = s.get("speaker", "")
                dur = s.get("duration_display", "0:00")
                turns = s.get("turn_count", 0)
                words = s.get("word_count", 0)
                parts.append(f"- {name}: {dur} ({turns} turns, {words} words)\n")
            parts.append("\n")
    # What the meeting is about (always show section)
    parts.append("**What the meeting is about**\n\n")
    about = (data.get("meeting_about") or "").strip()
    parts.append(about if about else "—\n\n")
    # Key discussions
    parts.append("**Key discussions**\n\n")
    discussions = data.get("key_discussions") or []
    if discussions:
        for d in discussions:
            if d:
                parts.append(f"- {d}\n")
        parts.append("\n")
    else:
        parts.append("—\n\n")
    # Planning
    parts.append("**Planning**\n\n")
    planning = data.get("planning") or []
    if planning:
        for p in planning:
            if p:
                parts.append(f"- {p}\n")
        parts.append("\n")
    else:
        parts.append("—\n\n")
    # Outcome
    parts.append("**Outcome**\n\n")
    outcome = (data.get("outcome") or "").strip()
    parts.append(outcome if outcome else "—\n\n")
    # Minutes of meeting (MOM)
    parts.append("**Minutes of meeting (MOM)**\n\n")
    mom = (data.get("mom") or "").strip()
    parts.append(mom if mom else "—\n\n")
    # Fallback: show decisions, action items, risks when present
    for label, key, fmt in (
        ("Decisions", "decisions", lambda d: d.get("decision", d)),
        ("Action items", "action_items", lambda a: f"{a.get('owner', '')}: {a.get('task', '')}" + (f" (due: {a.get('due_date', '')})" if a.get("due_date") else "")),
        ("Risks / open questions", "risks_or_open_questions", lambda r: r.get("item", r)),
    ):
        items = data.get(key, [])
        if items:
            parts.append(f"**{label}**\n\n")
            for it in items:
                if isinstance(it, dict):
                    parts.append(f"- {fmt(it)}\n")
            parts.append("\n")
    return "".join(parts).strip() if parts else "No summary available."


# Guardrail: only generation text is shown; strip any prompt/role leakage
_GENERATION_FORBIDDEN_LINE_PREFIXES = (
    "system:",
    "user:",
    "human:",
    "assistant:",
    "instruction:",
    "prompt:",
)


def _sanitize_generation_text(text: str) -> str:
    """Return text with only generation content; remove any line that looks like prompt/role leakage."""
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    kept = []
    for line in lines:
        s = line.lstrip()
        lower = s.lower()
        if any(lower.startswith(p) for p in _GENERATION_FORBIDDEN_LINE_PREFIXES):
            continue
        kept.append(line)
    return "".join(kept).strip()


def _valid_transcript_format(content: bytes) -> bool:
    """Return True if content has at least one line matching [HH:MM:SS] Speaker: text."""
    try:
        text = content.decode("utf-8", errors="replace")
        if not text.strip():
            return False
        for line in text.splitlines():
            if TRANSCRIPT_LINE_RE.match(line.strip()):
                return True
        return False
    except Exception:
        return False


def post_files(path: str, files_list):
    """POST multipart files to API."""
    url = f"{API_BASE}{path}"
    multipart = [("files", (f.name, f.getvalue(), "text/plain")) for f in files_list]
    return requests.post(url, files=multipart, timeout=120)


def run_main() -> None:
    """Render the Home page (main Meeting Intelligence Assistant UI)."""
    st.set_page_config(page_title="Meeting Intelligence Assistant", layout="wide", initial_sidebar_state="collapsed")
    st.title("🧠 Meeting Intelligence Assistant (RAG)")
    st.caption("Answers questions about discussions, decisions, and action items from your meeting.")

    # -------------------------
    # Generation (sample transcript)
    # -------------------------
    st.subheader("Generation")
    if "generated_transcript" not in st.session_state:
        st.session_state.generated_transcript = ""

    topic_input = st.text_input(
        "Topic (required)",
        value="",
        placeholder="e.g. Product planning, Q4 roadmap, feature priorities",
        key="gen_topic",
    )
    participants_input = st.text_input(
        "Participants (2–10): two users e.g. user1, user2 — for more users separate with comma",
        value="",
        placeholder="e.g. user1, user2  or  user1, user2, user3",
        key="gen_participants",
    )
    if st.session_state.get("gen_loading"):
        _gen_btn_red_loading()
        topic = (topic_input or "").strip()
        participants_raw = (participants_input or "").strip()
        participants_list = [n.strip() for n in participants_raw.split(",") if n.strip()] if participants_raw else []
        if topic and 2 <= len(participants_list) <= 10:
            payload = {
                "topic": topic,
                "participants": participants_list,
                "approx_lines": 80,
                "stream": True,
            }
            r = post_json("/generate_sample_transcript", payload, stream=True)
            if r.status_code != 200:
                st.error("Something went wrong.")
            else:
                def stream_chunks():
                    try:
                        for chunk in r.iter_content(chunk_size=8192, decode_unicode=False):
                            if chunk:
                                yield chunk.decode("utf-8", errors="replace")
                    except requests.exceptions.ChunkedEncodingError:
                        yield "\n\n[Error: Connection interrupted. Please try again.]"
                    except requests.exceptions.RequestException as e:
                        yield f"\n\n[Error: {str(e)}]"
                stream_box = st.container(height=260)
                with stream_box:
                    components.html(
                        """<script>
                        (function(){
                            var pdoc = window.parent.document;
                            function scrollAll() {
                                requestAnimationFrame(function(){
                                    pdoc.querySelectorAll('div').forEach(function(el){
                                        var s = window.parent.getComputedStyle(el);
                                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && 
                                            el.scrollHeight > el.clientHeight && 
                                            el.clientHeight > 100 && el.clientHeight < 350) {
                                            el.scrollTop = el.scrollHeight;
                                        }
                                    });
                                });
                            }
                            var obs = new MutationObserver(scrollAll);
                            obs.observe(pdoc.body, {childList:true, subtree:true, characterData:true});
                            setInterval(scrollAll, 50);
                            setTimeout(function(){ obs.disconnect(); }, 120000);
                        })();
                        </script>""",
                        height=0,
                    )
                    full = st.write_stream(stream_chunks())
                transcript = _sanitize_generation_text((full or "").strip())
                st.session_state.generated_transcript = transcript
                gen_filename = _topic_to_filename(topic)
                st.session_state.gen_download_filename = gen_filename
                st.session_state.gen_auto_download_done = False
            st.session_state.gen_loading = False
            st.rerun()
        else:
            st.error("Cannot be generated: enter topic and 2–10 participants.")
            st.session_state.gen_loading = False
            st.rerun()
    elif st.session_state.get("generated_transcript"):
        with st.container():
            _gen_btn_green_done()
            if st.button("Regenerate again", key="gen_regenerate"):
                st.session_state.generated_transcript = None
                st.session_state.gen_download_filename = None
                st.session_state.gen_auto_download_done = False
                st.rerun()
        _gen_fn = st.session_state.get("gen_download_filename", "sample_transcript.txt")
        transcript_bytes = st.session_state.generated_transcript.encode("utf-8")
        if transcript_bytes and len(transcript_bytes) < 500_000 and not st.session_state.get("gen_auto_download_done"):
            b64 = base64.b64encode(transcript_bytes).decode("ascii")
            components.html(
                f"""
                <a id="gen_autodl" href="data:text/plain;base64,{b64}" download="{_gen_fn}"></a>
                <script>
                (function() {{
                    var el = document.getElementById("gen_autodl");
                    if (el) setTimeout(function() {{ el.click(); }}, 800);
                }})();
                </script>
                """,
                height=0,
            )
            st.session_state.gen_auto_download_done = True
        st.caption("Download started automatically. If not, use the button below.")
        st.download_button(
            f"Download {_gen_fn}",
            data=st.session_state.generated_transcript,
            file_name=_gen_fn,
            mime="text/plain",
            key="download_sample",
        )
    else:
        gen_click = st.button("Generate sample transcript", key="gen_btn")
        if gen_click:
            topic = (topic_input or "").strip()
            participants_raw = (participants_input or "").strip()
            if not topic or not participants_raw:
                st.error("Cannot be generated: no context provided. Please enter both Topic and Participants.")
            else:
                participants_list = [n.strip() for n in participants_raw.split(",") if n.strip()]
                if len(participants_list) < 2:
                    st.error("Cannot be generated: enter at least 2 participants (e.g. user1, user2). Use comma for more.")
                elif len(participants_list) > 10:
                    st.error("Cannot be generated: maximum 10 participants allowed (comma-separated).")
                else:
                    st.session_state.gen_loading = True
                    st.rerun()

    # -------------------------
    # Ingestion (max 1 MB, transcript format required)
    # -------------------------
    st.subheader("Ingestion")
    _sample_path = Path(__file__).resolve().parent / "sample_transcript.txt"
    if _sample_path.exists():
        _sample_bytes = _sample_path.read_bytes()
        st.download_button(
            "Download sample format if above generation is not used",
            data=_sample_bytes,
            file_name="sample_transcript.txt",
            mime="text/plain",
            key="download_sample_static",
            help="Sample format doc for ingestion to this system for reference. Only this format allowed.",
        )
    st.caption("Upload a transcript (.txt, max 1 MB). Transcripts must have speaker labels and timestamps (e.g. [HH:MM:SS] Speaker: text).")
    ingest_uploads = st.file_uploader(
        "Choose transcript file",
        type=["txt"],
        accept_multiple_files=False,
        key="ingest_upload",
        label_visibility="collapsed",
        help="TXT only",
        max_upload_size=1,
    )

    ingest_ok = False
    ingest_error = None
    uploaded_file = None
    if ingest_uploads:
        uploaded_file = ingest_uploads[0] if isinstance(ingest_uploads, list) else ingest_uploads
        if uploaded_file:
            content = uploaded_file.getvalue()
            if len(content) > INGEST_MAX_BYTES:
                ingest_error = f"File exceeds 1 MB limit ({len(content) / (1024*1024):.2f} MB)."
            elif not _valid_transcript_format(content):
                ingest_error = "Incorrect file. Transcripts should be text files with speaker labels and timestamps (e.g. [HH:MM:SS] Speaker: text)."
            else:
                ingest_ok = True

    if ingest_error:
        st.error(ingest_error)

    if st.session_state.get("ingest_loading") and uploaded_file:
        _ingest_btn_red_loading()
        with st.spinner(""):
            r = post_files("/ingest", [uploaded_file])
            st.session_state.ingest_loading = False
            if r.status_code == 200:
                data = r.json()
                mid = data.get("meeting_id", "")
                st.session_state["meeting_id_input"] = mid
                st.session_state.ingest_done = True
                st.session_state.ingest_result = mid
            elif r.status_code == 409:
                st.session_state.ingest_done = False
                try:
                    detail = r.json().get("detail", {})
                    if isinstance(detail, dict):
                        mid = detail.get("meeting_id", "")
                        if mid:
                            st.session_state["meeting_id_input"] = mid
                        st.session_state.ingest_warning = "Document already ingested. Use the Meeting ID above to ask or summarize."
                    else:
                        st.session_state.ingest_warning = "Document already ingested."
                except Exception:
                    st.session_state.ingest_warning = "Document already ingested."
            else:
                st.session_state.ingest_done = False
                try:
                    err = r.json().get("detail", r.text)
                except Exception:
                    err = r.text
                st.session_state.ingest_error = "Incorrect file. Transcripts should be text files with speaker labels and timestamps (e.g. [HH:MM:SS] Speaker: text)." if "Incorrect file" in str(err) else "Something went wrong."
            st.rerun()
    elif st.session_state.get("ingest_done"):
        _ingest_btn_green_done()
        mid = st.session_state.get("ingest_result", "")
        if mid:
            st.success(f"Ingested. Meeting ID is {mid}")
        if st.button("📥 Ingest", key="ingest_again"):
            st.session_state.ingest_done = False
            st.session_state.ingest_result = None
            st.rerun()
    elif ingest_ok and uploaded_file:
        if st.button("📥 Ingest", key="ingest_btn"):
            st.session_state.ingest_loading = True
            st.session_state.ingest_done = False
            st.session_state.ingest_error = None
            st.session_state.ingest_warning = None
            st.rerun()
        if st.session_state.get("ingest_warning"):
            st.warning(st.session_state.ingest_warning)
            st.session_state.ingest_warning = None
        if st.session_state.get("ingest_error"):
            st.error(st.session_state.ingest_error)
            st.session_state.ingest_error = None

    # -------------------------
    # Meeting ID (auto-filled after ingestion)
    # -------------------------
    st.subheader("Meeting ID")
    if "meeting_id_input" not in st.session_state:
        st.session_state["meeting_id_input"] = ""
    st.caption("Auto-filled after ingestion. Edit to use a different meeting ID that is already ingested.")
    meeting_id = st.text_input("Meeting ID", placeholder="Meeting id", key="meeting_id_input", label_visibility="collapsed")

    # -------------------------
    # Summary of meeting (above Ask)
    # -------------------------
    st.subheader("Summary of meeting")
    if st.session_state.get("extract_summary_loading"):
        _extract_btn_red_loading()
        with st.spinner(""):
            r = post_json("/summary", {"meeting_id": st.session_state.get("extract_summary_meeting_id", "").strip()})
            st.session_state.extract_summary_loading = False
            if r.status_code == 200:
                st.session_state.extract_summary_done = True
                st.session_state.extract_summary_result = r.json()
            else:
                st.session_state.extract_summary_done = False
                st.session_state.extract_summary_error = True
            st.rerun()
    elif st.session_state.get("extract_summary_done"):
        _extract_btn_green_done()
        data = st.session_state.get("extract_summary_result")
        if data:
            st.markdown(summary_to_natural_language(data))
        if st.button("Clear", key="extract_clear"):
            st.session_state.extract_summary_done = False
            st.session_state.extract_summary_result = None
            st.rerun()
    else:
        if st.button("🧾 Extract Summary", key="extract_btn"):
            if not meeting_id or not meeting_id.strip():
                st.error("Please enter a Meeting ID above first.")
            else:
                st.session_state.extract_summary_loading = True
                st.session_state.extract_summary_meeting_id = meeting_id.strip()
                st.session_state.extract_summary_done = False
                st.session_state.extract_summary_error = False
                st.rerun()
        if st.session_state.get("extract_summary_error"):
            st.error("Something went wrong.")
            st.session_state.extract_summary_error = False

    # -------------------------
    # Ask (Type and press Enter)
    # -------------------------
    st.subheader("Ask")
    st.caption("Type and press Enter to ask about the meeting.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Show previous Q&A
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Below Ask: Type and press Enter field
    prompt = st.chat_input("Type and press Enter")
    if prompt:
        if not meeting_id or not meeting_id.strip():
            st.error("Please enter a Meeting ID above first (from script ingest).")
        else:
            prev_user = None
            for m in reversed(st.session_state.messages):
                if m.get("role") == "user":
                    prev_user = (m.get("content") or "").strip()
                    break
            payload = {
                "meeting_id": meeting_id.strip(),
                "question": prompt.strip(),
                "top_k": 10,
            }
            if prev_user:
                payload["previous_question"] = prev_user
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            r = post_json("/ask", payload)

            if r.status_code == 200:
                data = r.json()
                answer = data.get("answer", "")
                with st.chat_message("assistant"):
                    st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            else:
                with st.chat_message("assistant"):
                    if r.status_code == 400:
                        try:
                            err = r.json()
                            detail = err.get("detail", "")
                            if isinstance(detail, str) and ("disallowed" in detail.lower() or "query contains" in detail.lower()):
                                st.warning("I cannot answer: your query was flagged (e.g. prompt injection). Please rephrase.")
                                st.session_state.messages.append({"role": "assistant", "content": "(query flagged)"})
                                st.stop()
                        except Exception:
                            pass
                    err_content = "Something went wrong."
                    st.error(err_content)
                    st.session_state.messages.append({"role": "assistant", "content": err_content})
