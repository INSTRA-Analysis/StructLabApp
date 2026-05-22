"""Persistent list of recently opened .slab files.

Stored in ~/.structlab/recent_files.json — at most 8 entries,
pruned to paths that still exist on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

_RECENT_PATH = Path.home() / ".structlab" / "recent_files.json"
_MAX = 8


def load() -> list[str]:
    """Return recent paths (most recent first), pruned to files that exist."""
    try:
        data = json.loads(_RECENT_PATH.read_text(encoding="utf-8"))
        return [p for p in data if Path(p).exists()][:_MAX]
    except Exception:
        return []


def push(filepath: str) -> None:
    """Insert filepath at the front; keep at most _MAX entries."""
    paths = [p for p in load() if p != filepath]
    paths.insert(0, filepath)
    try:
        _RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RECENT_PATH.write_text(json.dumps(paths[:_MAX], indent=2), encoding="utf-8")
    except Exception:
        pass
