"""Loads bundled fixture findings so the pipeline runs offline & deterministically.

Fixtures use a relative ``hours_ago`` offset instead of absolute timestamps so
the sample data is always "fresh" relative to the current run. This lets the
24h window and cross-run dedup logic be demonstrated realistically.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..models import RawFinding, SourceType

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures"


class FixtureProvider:
    def __init__(self, fixture_dir: str | Path | None = None, now: datetime | None = None):
        self.fixture_dir = Path(fixture_dir) if fixture_dir else DEFAULT_FIXTURE_DIR
        self.now = now or datetime.now(UTC)
        self._by_source: dict[str, list[RawFinding]] = {}
        self._load()

    def _load(self) -> None:
        if not self.fixture_dir.exists():
            return
        for path in sorted(self.fixture_dir.glob("*.json")):
            entries = json.loads(path.read_text(encoding="utf-8"))
            for entry in entries:
                finding = self._to_finding(entry)
                self._by_source.setdefault(finding.source_name, []).append(finding)

    def _to_finding(self, entry: dict) -> RawFinding:
        hours_ago = float(entry.get("hours_ago", 1))
        published_at = self.now - timedelta(hours=hours_ago)
        return RawFinding(
            source_name=entry["source"],
            source_type=SourceType(entry["type"]),
            title=entry["title"],
            description=entry.get("description", ""),
            location=entry.get("location", "Österreich"),
            status=entry.get("status", "Unbekannt"),
            url=entry.get("url"),
            published_at=published_at,
            volume_eur=entry.get("volume_eur"),
            contact=entry.get("contact"),
            investor=entry.get("investor"),
        )

    def for_source(self, source_name: str) -> list[RawFinding]:
        return list(self._by_source.get(source_name, []))

    @property
    def total(self) -> int:
        return sum(len(v) for v in self._by_source.values())
