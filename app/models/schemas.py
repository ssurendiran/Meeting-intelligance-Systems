from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class IngestResponse(BaseModel):
    meeting_id: str = Field(..., description="Unique meeting identifier for this ingestion run")
    files_indexed: int = Field(..., ge=0)
    chunks_indexed: int = Field(..., ge=0)


class AskRequest(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID returned by /ingest")
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = Field(None, description="Override retrieval top_k (defaults to config)")


class Citation(BaseModel):
    file: str
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    retrieved: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Debug: retrieved chunks with metadata (safe for take-home; disable in prod)",
    )


class SummaryRequest(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID returned by /ingest")


class DecisionItem(BaseModel):
    decision: str
    evidence: str = Field(..., description="Must match an allowed evidence value e.g. transcript1.txt:1-8")


class ActionItem(BaseModel):
    owner: str
    task: str
    due_date: Optional[str] = Field(None, description="If present, extracted due date text (free-form)")
    evidence: str


class RiskItem(BaseModel):
    item: str
    evidence: str


class SummaryResponse(BaseModel):
    decisions: List[DecisionItem] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    risks_or_open_questions: List[RiskItem] = Field(default_factory=list)
