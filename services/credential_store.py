"""Persist CrowdSky credentials to disk.

Desktop: JSON file at ``~/.crowdsky/credentials.json``.
Android: placeholder for SharedPreferences (future).
"""

import json
import os
import sys
from pathlib import Path


def _cred_path():
    if sys.platform == "linux" and "ANDROID_ARGUMENT" in os.environ:
        return Path(os.environ.get("ANDROID_PRIVATE", ".")) / "credentials.json"
    return Path.home() / ".crowdsky" / "credentials.json"


def save_credentials(username, password):
    path = _cred_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"username": username, "password": password}))


def load_credentials():
    """Return (username, password) or (None, None) if not stored."""
    path = _cred_path()
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text())
        return data.get("username"), data.get("password")
    except (json.JSONDecodeError, KeyError):
        return None, None


def clear_credentials():
    path = _cred_path()
    if path.exists():
        path.unlink()
