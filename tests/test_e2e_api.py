import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Resolve paths from repo root so tests pass when run from tests/ or project root
REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TRANSCRIPT = REPO_ROOT / "sample_data" / "transcript1.txt"


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _log(item, title: str, request: dict, response: dict):
    """
    Store logs on the test item so conftest can attach to pytest-html report.
    """
    logs = getattr(item, "_api_logs", [])
    logs.append({"title": title, "request": request, "response": response})
    item._api_logs = logs


def _ingest_one(client: TestClient, item, transcript_path: str) -> str:
    p = Path(transcript_path)
    assert p.exists(), f"Missing test transcript: {p}"

    with p.open("rb") as f:
        files = [("files", (p.name, f, "text/plain"))]
        req_log = {"method": "POST", "url": "/ingest", "files": [p.name]}
        resp = client.post("/ingest", files=files)

    resp_log = {"status_code": resp.status_code, "json": resp.json() if resp.headers.get("content-type","").startswith("application/json") else resp.text}
    _log(item, "POST /ingest", req_log, resp_log)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "meeting_id" in data
    assert data["files_indexed"] == 1
    assert data["chunks_indexed"] > 0
    return data["meeting_id"]


def _assert_citations_within_retrieved(payload: dict):
    from app.guardrails.citations import allowed_ranges, citation_overlaps_range

    citations = payload.get("citations", [])
    retrieved = payload.get("retrieved", [])
    assert isinstance(retrieved, list) and retrieved, "Expected retrieved chunks"

    allowed = allowed_ranges(retrieved)
    for c in citations:
        assert citation_overlaps_range(
            c["file"], c["line_start"], c["line_end"], allowed
        ), f"Citation {c['file']}:{c['line_start']}-{c['line_end']} not within retrieved ranges"


def _parse_sse_events(body: str) -> list:
    """Parse SSE body into list of event dicts (data: {...} lines)."""
    events = []
    for block in body.strip().split("\n\n"):
        block = block.strip()
        if not block or not block.startswith("data:"):
            continue
        payload = block[5:].strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return events


def test_ingest_and_ask_decisions(client: TestClient, request):
    meeting_id = _ingest_one(client, request.node, str(SAMPLE_TRANSCRIPT))

    ask_req = {"meeting_id": meeting_id, "question": "What were the main topics?"}
    resp = client.post("/ask", json=ask_req)

    _log(
        request.node,
        "POST /ask",
        {"method": "POST", "url": "/ask", "json": ask_req},
        {"status_code": resp.status_code, "json": resp.json()},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert isinstance(data.get("answer"), str) and data["answer"].strip()
    assert isinstance(data.get("citations"), list)
    assert len(data["citations"]) >= 1, "Expected at least one citation"
    assert isinstance(data.get("retrieved"), list) and len(data["retrieved"]) > 0

    _assert_citations_within_retrieved(data)


def test_summary_structure_and_evidence(client: TestClient, request):
    meeting_id = _ingest_one(client, request.node, str(SAMPLE_TRANSCRIPT))

    sum_req = {"meeting_id": meeting_id}
    resp = client.post("/summary", json=sum_req)

    _log(
        request.node,
        "POST /summary",
        {"method": "POST", "url": "/summary", "json": sum_req},
        {"status_code": resp.status_code, "json": resp.json()},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "decisions" in data and isinstance(data["decisions"], list)
    assert "action_items" in data and isinstance(data["action_items"], list)
    assert "risks_or_open_questions" in data and isinstance(data["risks_or_open_questions"], list)

    for group in ["decisions", "action_items", "risks_or_open_questions"]:
        for item in data[group]:
            ev = item.get("evidence")
            assert isinstance(ev, str)
            assert ":" in ev and "-" in ev, f"Evidence format invalid: {ev}"


def test_ask_unknown_question_refuses(client: TestClient, request):
    meeting_id = _ingest_one(client, request.node, str(SAMPLE_TRANSCRIPT))

    ask_req = {"meeting_id": meeting_id, "question": "What is the CEO's salary?"}
    resp = client.post("/ask", json=ask_req)

    _log(
        request.node,
        "POST /ask (unknown question)",
        {"method": "POST", "url": "/ask", "json": ask_req},
        {"status_code": resp.status_code, "json": resp.json()},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["answer"] == "Not found in transcript."
    assert data["citations"] == []


# -------------------------
# Async Ingest + Job Status
# -------------------------


def test_ingest_async_and_job_status(client: TestClient, request):
    p = SAMPLE_TRANSCRIPT
    assert p.exists(), f"Missing transcript: {p}"

    with p.open("rb") as f:
        files = [("files", (p.name, f, "text/plain"))]
        resp = client.post("/ingest_async", files=files)

    _log(
        request.node,
        "POST /ingest_async",
        {"method": "POST", "url": "/ingest_async", "files": [p.name]},
        {"status_code": resp.status_code, "json": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "job_id" in data
    assert "meeting_id" in data
    job_id = data["job_id"]

    # Poll job status until done or failed (max ~15s)
    for _ in range(30):
        status_resp = client.get(f"/jobs/{job_id}")
        assert status_resp.status_code == 200, status_resp.text
        job = status_resp.json()
        if job["status"] == "done":
            assert job["chunks_indexed"] > 0, "Expected chunks indexed"
            _log(
                request.node,
                "GET /jobs/{job_id} (done)",
                {"method": "GET", "url": f"/jobs/{job_id}"},
                {"status_code": status_resp.status_code, "json": job},
            )
            return
        if job["status"] == "failed":
            pytest.fail(f"Job failed: {job.get('error', 'unknown')}")
        time.sleep(0.5)

    pytest.fail("Job did not complete within timeout")


# -------------------------
# Summary edge cases
# -------------------------


def test_summary_invalid_meeting_id_returns_400(client: TestClient, request):
    resp = client.post("/summary", json={"meeting_id": "not-a-uuid"})

    _log(
        request.node,
        "POST /summary (invalid meeting_id)",
        {"method": "POST", "url": "/summary", "json": {"meeting_id": "not-a-uuid"}},
        {"status_code": resp.status_code, "json": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text},
    )

    assert resp.status_code == 400, resp.text
    data = resp.json()
    assert "detail" in data


def test_summary_unknown_meeting_id_returns_empty_lists(client: TestClient, request):
    # Valid UUID that was never ingested
    unknown_meeting_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post("/summary", json={"meeting_id": unknown_meeting_id})

    _log(
        request.node,
        "POST /summary (unknown meeting_id)",
        {"method": "POST", "url": "/summary", "json": {"meeting_id": unknown_meeting_id}},
        {"status_code": resp.status_code, "json": resp.json()},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decisions"] == []
    assert data["action_items"] == []
    assert data["risks_or_open_questions"] == []


def test_ask_unknown_or_invalid_meeting_id_returns_not_found(client: TestClient, request):
    # /ask does not validate UUID format; unknown/invalid meeting_id yields no retrieval → refusal
    resp = client.post("/ask", json={"meeting_id": "not-a-uuid", "question": "What was decided?"})

    _log(
        request.node,
        "POST /ask (invalid/unknown meeting_id)",
        {"method": "POST", "url": "/ask", "json": {"meeting_id": "not-a-uuid", "question": "What was decided?"}},
        {"status_code": resp.status_code, "json": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["answer"] == "Not found in transcript."
    assert data["citations"] == []


