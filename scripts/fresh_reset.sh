#!/usr/bin/env bash
# Down all, remove persisted data, bring up stack.
# Usage: bash scripts/fresh_reset.sh   (run from repo root)
#
# Ingest via UI (http://localhost:8501) or API (POST /ingest) after the stack is up.

set -e
cd "$(dirname "$0")/.."

echo "Syncing dependencies (uv sync)..."
uv sync

echo "Stopping and removing containers and volumes..."
docker-compose down -v 2>/dev/null || true

echo "Removing persisted data..."
rm -rf data/uploads
rm -f data/history.db
mkdir -p data

echo "Removing test artifacts (reports, upload caches)..."
rm -rf tests/reports
find tests/data/uploads -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true
mkdir -p tests/data/uploads

echo "Starting stack..."
docker-compose up -d

echo "Waiting for API..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "API ready."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "API did not become ready in time. Run 'docker-compose up -d' and check logs."
    exit 0
  fi
  sleep 2
done

echo ""
echo "Done. Fresh state."
echo "  - Open UI: http://localhost:8501 — ingest a transcript, then Ask / Summary"
echo "  - Or POST /ingest with a transcript file, then run E2E: uv run pytest tests/test_e2e_api.py -v"
echo ""
