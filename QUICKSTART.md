# Quick Start

Get the Meeting Intelligence Platform running in minutes.

---

## Prerequisites

- **Python 3.12**
- **uv** (package manager) — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **Docker** 
- **OpenAI API key**

---

##  Docker Compose (recommended)

Everything runs in containers: Qdrant, API, and Streamlit UI.

```bash
# 1. Copy env and add your OpenAI key
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-...

# 2. Start all services
docker compose up -d

# 3. Open the UI
# http://localhost:8501
```

| Service | URL |
|---------|-----|
| UI | http://localhost:8501 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Qdrant | http://localhost:6333 |

---


## First run: generate → ingest → ask

### 1. Generate a sample transcript (optional)

Creates a synthetic meeting for testing.

```bash
curl -X POST http://localhost:8000/generate_sample_transcript \
  -H "Content-Type: application/json" \
  -d '{"topic": "Q2 product launch planning", "participants": "Alex, Sam, Jordan"}'
```

### 2. Ingest a transcript

Upload a `.txt` file in this format:

```
[00:00:00] Alex: Let's kick off the product sync.
[00:00:12] Sam: I'd suggest we target June 15.
[00:00:25] Jordan: Marketing needs at least three weeks.
```

```bash
curl -X POST http://localhost:8000/ingest \
  -F "file=@ui/sample_transcript.txt"
```

Response includes `meeting_id` — use it to ask questions.

### 3. Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"meeting_id": "YOUR_MEETING_ID", "question": "What was the launch date decided?"}'
```

---

## UI workflow

1. Open http://localhost:8501
2. **Generate** — enter topic + participants to create a synthetic transcript
3. **Upload** — ingest a transcript file (or use the generated one)
4. **Ask** — enter your question and get citation-backed answers

---

## Transcript format

Each line must match: `[HH:MM:SS] Speaker: text`

```text
[00:00:00] Alex: Hello everyone.
[00:00:05] Sam: Hi Alex.
[00:01:30] Jordan: Let's discuss the roadmap.
```

- Max file size: 1 MB
- Invalid format → HTTP 400

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `OPENAI_API_KEY` missing | Add to `.env` |
| Connection refused to Qdrant | Run `docker compose up -d qdrant` |
| Port already in use | Change ports in `docker-compose.yaml` or kill process |
| UI can't reach API | Ensure `API_BASE` / `QDRANT_URL` match your setup (Docker vs local) |

---

## Next steps

- API docs: http://localhost:8000/docs
- Full architecture: [README.md](README.md)
