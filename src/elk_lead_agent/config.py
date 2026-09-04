"""Configuration loading and typed access."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import SourceType

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


@dataclass(frozen=True)
class SourceConfig:
    name: str
    type: SourceType
    enabled: bool = True
    live: bool = False


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    keywords: tuple[str, ...]


@dataclass
class Config:
    threshold_lead: int
    window_hours: int
    volume_threshold_eur: float
    points: dict[str, int]
    hotel_or_employee_categories: tuple[str, ...]
    categories: dict[str, Category]
    search_terms: tuple[str, ...]
    timber_keywords: tuple[str, ...]
    submission_keywords: tuple[str, ...]
    developers: dict[str, str]
    sources: list[SourceConfig] = field(default_factory=list)

    @property
    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate the YAML configuration into a typed :class:`Config`."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    scoring = raw.get("scoring", {})
    categories: dict[str, Category] = {}
    for key, spec in raw.get("categories", {}).items():
        categories[key] = Category(
            key=key,
            label=spec["label"],
            keywords=tuple(spec.get("keywords", [])),
        )

    sources: list[SourceConfig] = []
    for s in raw.get("sources", []):
        sources.append(
            SourceConfig(
                name=s["name"],
                type=SourceType(s["type"]),
                enabled=bool(s.get("enabled", True)),
                live=bool(s.get("live", False)),
            )
        )

    return Config(
        threshold_lead=int(raw.get("threshold_lead", 60)),
        window_hours=int(raw.get("window_hours", 24)),
        volume_threshold_eur=float(scoring.get("volume_threshold_eur", 2_000_000)),
        points=dict(scoring.get("points", {})),
        hotel_or_employee_categories=tuple(raw.get("hotel_or_employee_categories", [])),
        categories=categories,
        search_terms=tuple(raw.get("search_terms", [])),
        timber_keywords=tuple(raw.get("timber_keywords", [])),
        submission_keywords=tuple(raw.get("submission_keywords", [])),
        developers=dict(raw.get("developers", {})),
        sources=sources,
    )
