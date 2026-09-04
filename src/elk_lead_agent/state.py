"""Persistent state so a project is only reported as 'new' once."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "state" / "seen.json"


class StateStore:
    """Tracks fingerprints of projects that have already been reported."""

    def __init__(self, path: str | Path | None = None, enabled: bool = True):
        self.path = Path(path) if path else DEFAULT_STATE_PATH
        self.enabled = enabled
        self._seen: dict[str, str] = {}
        if self.enabled and self.path.exists():
            try:
                self._seen = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._seen = {}

    def is_seen(self, fingerprint: str) -> bool:
        if not self.enabled:
            return False
        return fingerprint in self._seen

    def mark_seen(self, fingerprints: list[str]) -> None:
        if not self.enabled:
            return
        now = datetime.now(UTC).isoformat()
        for fp in fingerprints:
            self._seen.setdefault(fp, now)

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._seen, indent=2), encoding="utf-8")

    def reset(self) -> None:
        self._seen = {}
        if self.enabled and self.path.exists():
            self.path.unlink()
