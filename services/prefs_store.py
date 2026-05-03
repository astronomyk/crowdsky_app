"""Persist user UI preferences to disk.

Desktop: JSON file at ``~/.crowdsky/prefs.json``.
Android: under the app's private dir.

Currently stores:

- ``compass_altitudes`` — list[8] of horizon-mask altitudes (deg)

Add new keys here as more prefs become persistent.  Reads default to
sensible fallbacks so the file can be missing or partially-filled.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _prefs_path() -> Path:
    if sys.platform == "linux" and "ANDROID_ARGUMENT" in os.environ:
        return Path(os.environ.get("ANDROID_PRIVATE", ".")) / "prefs.json"
    return Path.home() / ".crowdsky" / "prefs.json"


def _read() -> dict:
    path = _prefs_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def load_compass_altitudes() -> list[float]:
    """Return the 8 stored compass altitudes, or all-zeros if unset."""
    data = _read()
    raw = data.get("compass_altitudes")
    if not isinstance(raw, list) or len(raw) != 8:
        return [0.0] * 8
    out = []
    for v in raw:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def save_compass_altitudes(alts) -> None:
    if alts is None:
        return
    alts_list = [float(v) for v in alts]
    if len(alts_list) != 8:
        return
    data = _read()
    data["compass_altitudes"] = alts_list
    _write(data)
