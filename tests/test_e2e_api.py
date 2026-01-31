from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app


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
    citations = payload.get("citations", [])
    retrieved = payload.get("retrieved", [])
    assert isinstance(retrieved, list) and retrieved, "Expected retrieved chunks"

    allowed = {}
    for r in retrieved:
        f = r["file"]
        a = r["line_start"]
        b = r["line_end"]
        allowed.setdefault(f, []).append((a, b))

    def overlaps(a1, a2, b1, b2):
        return not (a2 < b1 or b2 < a1)

    for c in citations:
        f = c["file"]
        cs, ce = c["line_start"], c["line_end"]
        assert f in allowed, f"Citation file {f} not in retrieved files"
        ok = any(overlaps(cs, ce, a, b) for (a, b) in allowed[f])
        assert ok, f"Citation {f}:{cs}-{ce} not within retrieved ranges {allowed[f]}"


def test_health(client: TestClient, request):
    resp = client.get("/health")
    _log(
        request.node,
        "GET /health",
        {"method": "GET", "url": "/health"},
        {"status_code": resp.status_code, "json": resp.json()},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ingest_and_ask_decisions(client: TestClient, request):
    meeting_id = _ingest_one(client, request.node, "sample_data/transcript1.txt")

    ask_req = {"meeting_id": meeting_id, "question": "What decisions were made?"}
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
    meeting_id = _ingest_one(client, request.node, "sample_data/transcript1.txt")

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
    meeting_id = _ingest_one(client, request.node, "sample_data/transcript1.txt")

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
