#!/usr/bin/env python3
"""Print ingestion and API limits (from config and main app). Run from repo root: uv run python scripts/print_limits.py"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings

# Rate limit is hardcoded in main.py
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

def main():
    """Print ingestion and API limits (MAX_FILE_KB, CHUNK_TURNS, RETRIEVE_TOP_K, rate limit)."""
    print("Ingestion & API limits")
    print("----------------------")
    print(f"  MAX_FILE_KB          = {settings.max_file_kb} KB (max size per uploaded file)")
    print(f"  CHUNK_TURNS           = {settings.chunk_turns} (turns per chunk)")
    print(f"  RETRIEVE_TOP_K        = {settings.retrieve_top_k} (default retrieval top_k)")
    print(f"  Rate limit            = {RATE_LIMIT_REQUESTS} requests / {RATE_LIMIT_WINDOW_SECONDS} s (per client IP)")
    print("")
    print("Env: MAX_FILE_KB, CHUNK_TURNS, RETRIEVE_TOP_K (see .env.example)")


if __name__ == "__main__":
    main()
