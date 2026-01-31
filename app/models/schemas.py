from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class IngestResponse(BaseModel):
    meeting_id: str
    files_indexed: int
    chunks_indexed: int


class AskRequest(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID returned by /ingest")
    question: str
    top_k: Optional[int] = None


class Citation(BaseModel):
    file: str
    line_start: int
    line_end: int


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    retrieved: Optional[List[Dict[str, Any]]] = None

class SummaryRequest(BaseModel):
    meeting_id: str


class SummaryResponse(BaseModel):
    decisions: list[dict]
    action_items: list[dict]
    risks_or_open_questions: list[dict]
