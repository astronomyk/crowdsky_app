"""Persistent journal of uploaded chunk keys.

Records which chunk_keys have been successfully uploaded to the CrowdSky
server.  Used as a fast fallback when the server fetch is slow or
unavailable.  The server is authoritative — when a fresh server fetch
succeeds, the journal is synced down to match.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_PATH = Path(os.path.expanduser("~/.crowdsky/uploaded_chunks.json"))

_lock = threading.Lock()


def load_uploaded_chunks():
    """Load chunk keys from the local journal.

    Returns
    -------
    set[str]
        Chunk keys, or empty set if the file is missing or corrupt.
    """
    try:
        with open(JOURNAL_PATH, "r") as f:
            data = json.load(f)
        return set(data.get("chunks", []))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return set()


def record_uploaded_chunk(chunk_key):
    """Append a chunk key to the journal (thread-safe, idempotent).

    Parameters
    ----------
    chunk_key : str
        e.g. ``"20250731.79_HP154750"``
    """
    with _lock:
        existing = load_uploaded_chunks()
        existing.add(chunk_key)
        _write(existing)


def sync_with_server(server_chunk_keys):
    """Replace journal contents with the server's chunk keys.

    Called after a successful server fetch so the journal stays in sync.
    If a user deletes a stack from the server, the next sync removes it
    from the journal — allowing that block to be re-stacked.

    Parameters
    ----------
    server_chunk_keys : set[str]
    """
    with _lock:
        _write(server_chunk_keys)


def get_known_chunks(server_chunk_keys=None):
    """Return the best-available set of known uploaded chunk keys.

    If *server_chunk_keys* is provided and non-empty, sync the journal
    and return them (server is authoritative).  Otherwise fall back to
    the journal contents.

    Parameters
    ----------
    server_chunk_keys : set[str] or None

    Returns
    -------
    set[str]
    """
    if server_chunk_keys:
        sync_with_server(server_chunk_keys)
        return set(server_chunk_keys)
    return load_uploaded_chunks()


def _write(chunks):
    """Write the chunk set to disk."""
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "chunks": sorted(chunks),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    tmp = JOURNAL_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(JOURNAL_PATH)
