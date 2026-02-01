"""In-memory job store for async ingest: track status (queued / running / done / failed) and results."""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Job:
    """A single async ingest job: job_id, meeting_id, status (queued | running | done | failed), timestamps, and optional error or counts.
    Why available: In-memory store for /ingest_async so clients can poll /job_status until the job completes or fails."""

    job_id: str
    meeting_id: str
    status: str  # queued | running | done | failed
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    files_indexed: int = 0
    chunks_indexed: int = 0

# In-memory store (MVP). In production: Redis/DB.
JOBS: Dict[str, Job] = {}
