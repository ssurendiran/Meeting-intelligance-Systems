"""
Duplicate ingestion check by content hash.
Prevents re-ingesting the same transcript; returns existing meeting_id if content was already ingested.
"""
import hashlib
import json
import os
from typing import List, Optional


HASH_INDEX_FILENAME = "ingested_content_hashes.json"


def content_hash(contents: List[bytes]) -> str:
    """Compute SHA-256 of combined upload (deterministic order). Single file = hash of that content.
    Why available: Used to detect duplicate uploads so we can return existing meeting_id instead of re-indexing."""
    combined = b"\x00".join(contents) if contents else b""
    return hashlib.sha256(combined).hexdigest()


def _index_path(data_root: str) -> str:
    """Return the path to the ingested content-hash index file (hash -> meeting_id). Used by get_existing_meeting_id and register_ingested."""
    return os.path.join(data_root, HASH_INDEX_FILENAME)


def get_existing_meeting_id(content_hash_hex: str, data_root: str) -> Optional[str]:
    """Return meeting_id if this content was already ingested, else None.
    Why available: Ingest flow checks this first so duplicate uploads return the existing meeting without re-indexing."""
    path = _index_path(data_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("hashes") or {}).get(content_hash_hex)
    except Exception:
        return None


def register_ingested(content_hash_hex: str, meeting_id: str, data_root: str) -> None:
    """Record that this content hash was ingested under meeting_id.
    Why available: After successful ingest we persist the mapping so future uploads of the same content are detected as duplicates."""
    path = _index_path(data_root)
    os.makedirs(data_root, exist_ok=True)
    data = {"hashes": {}}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    if not isinstance(data.get("hashes"), dict):
        data["hashes"] = {}
    data["hashes"][content_hash_hex] = meeting_id
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
