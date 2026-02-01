from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class IngestResponse(BaseModel):
    meeting_id: str = Field(..., description="Unique meeting identifier for this ingestion run")
    files_indexed: int = Field(..., ge=0)
    chunks_indexed: int = Field(..., ge=0)


class AskRequest(BaseModel):
    """Request body for /ask and /ask_stream. Why available: Carries meeting_id, question, and optional follow-up/speaker filters."""

    meeting_id: str = Field(..., description="Meeting ID returned by /ingest")
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = Field(None, description="Override retrieval top_k (defaults to config)")
    previous_question: Optional[str] = Field(None, description="Previous user question (for follow-ups; used to infer timestamp filter)")
    speaker_filter: Optional[str] = Field(None, description="Filter retrieval to chunks where this speaker appears (case-insensitive)")


class Citation(BaseModel):
    """A single citation: file and line range. Why available: Returned with answers so users can verify which transcript lines support the answer."""

    file: str
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)


class AskResponse(BaseModel):
    """Response for /ask: answer text, citations, and optional retrieved chunks. Why available: Standard shape for Q&A so UI can render answer and citations."""

    answer: str
    citations: List[Citation] = Field(default_factory=list)
    retrieved: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Debug: retrieved chunks with metadata (safe for take-home; disable in prod)",
    )


class SummaryRequest(BaseModel):
    """Request body for /summary. Why available: Carries meeting_id so the API knows which meeting to summarize."""

    meeting_id: str = Field(..., description="Meeting ID returned by /ingest")


class DecisionItem(BaseModel):
    """One decision with evidence. Why available: Part of summary so users see decisions with transcript-backed evidence."""

    decision: str
    evidence: str = Field(..., description="Must match an allowed evidence value e.g. transcript1.txt:1-8")


class ActionItem(BaseModel):
    """One action item (owner, task, due_date, evidence). Why available: Part of summary so users see action items with transcript-backed evidence."""

    owner: str
    task: str
    due_date: Optional[str] = Field(None, description="If present, extracted due date text (free-form)")
    evidence: str


class RiskItem(BaseModel):
    """One risk or open question with evidence. Why available: Part of summary so users see risks with transcript-backed evidence."""

    item: str
    evidence: str


class SpeakerParticipationItem(BaseModel):
    """Per-speaker stats (duration, turn/word counts). Why available: Part of summary so users see who talked most/least."""

    speaker: str = Field(..., description="Speaker name")
    duration_display: str = Field(..., description="Speaking time e.g. 2:30")
    turn_count: int = Field(..., ge=0)
    word_count: int = Field(..., ge=0)


class SummaryResponse(BaseModel):
    """Response for /summary: structured meeting summary (about, discussions, decisions, action items, risks, speaker participation). Why available: Standard shape so UI can render the full summary."""

    meeting_about: Optional[str] = Field(None, description="What the meeting is about")
    key_discussions: List[str] = Field(default_factory=list, description="Key discussion points")
    planning: List[str] = Field(default_factory=list, description="Planning / timeline items")
    outcome: Optional[str] = Field(None, description="Key outcomes and next steps")
    mom: Optional[str] = Field(None, description="Minutes of meeting narrative")
    decisions: List[DecisionItem] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    risks_or_open_questions: List[RiskItem] = Field(default_factory=list)
    start_time: Optional[str] = Field(None, description="Meeting start time e.g. 00:00:00")
    end_time: Optional[str] = Field(None, description="Meeting end time e.g. 00:12:45")
    call_duration: Optional[str] = Field(None, description="Total call duration e.g. 12:34")
    speaker_participation: List[SpeakerParticipationItem] = Field(
        default_factory=list,
        description="Per-speaker duration and turn/word counts (who talked most/least)",
    )


class IngestAsyncResponse(BaseModel):
    """Response for POST /ingest_async: job_id and meeting_id. Why available: Clients poll /job_status with job_id until done."""

    job_id: str
    meeting_id: str


class JobStatusResponse(BaseModel):
    """Response for GET /job_status: job state and counts or error. Why available: Lets clients know when async ingest finished or failed."""

    job_id: str
    meeting_id: str
    status: str
    files_indexed: int = 0
    chunks_indexed: int = 0
    error: Optional[str] = None


class LimitsResponse(BaseModel):
    """Response for GET /limits: API limits (file size, chunk/retrieval, rate limit). Why available: Lets UI display or enforce limits before upload/ask."""

    max_file_kb: int = Field(..., description="Max upload file size in KB")
    chunk_turns: int = Field(..., description="Turns per chunk")
    retrieve_top_k: int = Field(..., description="Default retrieval top_k")
    rate_limit_requests: int = Field(..., description="Rate limit requests per window")
    rate_limit_window_seconds: int = Field(..., description="Rate limit window in seconds")


class GenerateSampleTranscriptRequest(BaseModel):
    """Request for POST /generate_sample_transcript. Why available: Lets clients request a demo transcript by topic/participants for testing ingest and RAG."""

    topic: Optional[str] = Field(None, description="Meeting topic (e.g. product planning, sprint review)")
    participants: Optional[List[str]] = Field(None, description="Exact list of speaker names; transcript must use only these, no others")
    num_speakers: int = Field(3, ge=2, le=6, description="Number of speakers (used only if participants not provided)")
    approx_lines: int = Field(80, ge=20, le=200, description="Approximate number of lines (keeps file under 1 MB)")
    stream: bool = Field(False, description="If true, response is streamed as text/plain (only LLM output)")


class GenerateSampleTranscriptResponse(BaseModel):
    """Response for /generate_sample_transcript (non-streamed). Why available: Returns full transcript when stream=False."""

    transcript: str = Field(..., description="Generated transcript in [HH:MM:SS] Speaker: text format")
