"""Domain models shared across the orchestrator and its agents."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    """High-level grouping of a public source."""

    TENDER = "tender"          # Behörden & Vergabeplattformen
    ZONING = "zoning"          # Widmungs- und Bauverfahren
    DEVELOPER = "developer"    # Immobilienentwickler
    HOTEL = "hotel"            # Hotel- und Tourismusbereich
    PRESS = "press"            # Presse & Fachportale


class Potential(StrEnum):
    """Qualitative potential shown in the report (Potenzial)."""

    HOCH = "Hoch"
    MITTEL = "Mittel"
    NIEDRIG = "Niedrig"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RawFinding(BaseModel):
    """A candidate project as returned by a collector agent, before analysis."""

    source_name: str
    source_type: SourceType
    title: str
    description: str = ""
    location: str = "Österreich"
    status: str = "Unbekannt"
    url: str | None = None
    published_at: datetime = Field(default_factory=_utcnow)
    volume_eur: float | None = None
    contact: str | None = None
    investor: str | None = None

    @property
    def text(self) -> str:
        """Concatenated searchable text used for keyword matching."""
        parts = [self.title, self.description, self.status, self.location]
        if self.investor:
            parts.append(self.investor)
        return " \n ".join(p for p in parts if p)

    @property
    def fingerprint(self) -> str:
        """Stable id used for cross-run deduplication."""
        basis = (self.url or f"{self.source_name}:{self.title}:{self.location}").strip().lower()
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


class ScoreBreakdown(BaseModel):
    """Transparent per-criterion scoring, so a human can audit the total."""

    volume_over_threshold: int = 0
    timber_or_modular: int = 0
    submission_imminent: int = 0
    investor_known: int = 0
    hotel_or_employee_housing: int = 0

    @property
    def total(self) -> int:
        return (
            self.volume_over_threshold
            + self.timber_or_modular
            + self.submission_imminent
            + self.investor_known
            + self.hotel_or_employee_housing
        )

    def reasons(self) -> list[str]:
        labels = {
            "volume_over_threshold": "Projektvolumen > 2 Mio. €",
            "timber_or_modular": "Holz-/Modulbau erwähnt",
            "submission_imminent": "Einreichung steht bevor",
            "investor_known": "Investor bekannt",
            "hotel_or_employee_housing": "Hotel / Mitarbeiterquartier",
        }
        out: list[str] = []
        for field, label in labels.items():
            pts = getattr(self, field)
            if pts:
                out.append(f"{label} (+{pts})")
        return out


class ScoredProject(BaseModel):
    """A finding enriched with categories, score and report-ready fields."""

    finding: RawFinding
    fingerprint: str
    categories: list[str] = Field(default_factory=list)      # category keys
    category_labels: list[str] = Field(default_factory=list)  # human labels
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    is_timber_or_modular: bool = False

    # Enriched, report-ready fields.
    potential: Potential = Potential.NIEDRIG
    elk_relevance: Potential = Potential.NIEDRIG
    contact: str | None = None
    volume_estimate_eur: float | None = None
    next_action: str = ""
    is_lead: bool = False

    @property
    def score(self) -> int:
        return self.breakdown.total


class RunReport(BaseModel):
    """The full result of one orchestrator run (a morning report)."""

    generated_at: datetime = Field(default_factory=_utcnow)
    window_hours: int = 24
    threshold_lead: int = 60
    projects: list[ScoredProject] = Field(default_factory=list)
    sources_queried: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def leads(self) -> list[ScoredProject]:
        return [p for p in self.projects if p.score >= self.threshold_lead]
