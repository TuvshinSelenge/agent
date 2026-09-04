"""Concrete collector agents, one class per source group, plus a factory.

Only TED ships a best-effort live fetcher (it exposes a public search API). The
other collectors fall back to bundled fixtures, which keeps the demonstration
deterministic while leaving a clean extension point for real integrations.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..config import Config, SourceConfig
from ..models import RawFinding, SourceType
from .base import SourceAgent
from .fixtures import FixtureProvider

TED_API_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_TIMEOUT_S = 8.0


class TenderAgent(SourceAgent):
    """Behörden & Vergabeplattformen (ANKÖ, Auftrag.at, TED, Bundesbeschaffung, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        if self.source.name.startswith("TED"):
            return self._fetch_ted()
        return []

    def _fetch_ted(self) -> list[RawFinding]:
        # TED expert search: Austria + our free-text search terms.
        terms = " OR ".join(f'"{t}"' for t in self.config.search_terms[:8])
        query = f"(FT=({terms})) AND (CY=AUT)"
        payload = {
            "query": query,
            "fields": ["ND", "TI", "PD", "TW", "RC"],
            "limit": 25,
        }
        with httpx.Client(timeout=TED_TIMEOUT_S) as client:
            resp = client.post(TED_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        findings: list[RawFinding] = []
        for notice in data.get("notices", []):
            title = _first(notice.get("TI")) or "TED-Ausschreibung"
            published = _parse_ted_date(_first(notice.get("PD")))
            kwargs = {
                "source_name": self.source.name,
                "source_type": SourceType.TENDER,
                "title": title,
                "description": _first(notice.get("TW")) or "",
                "location": _first(notice.get("TW")) or "Österreich",
                "status": "EU-Ausschreibung",
                "url": f"https://ted.europa.eu/udl?uri=TED:NOTICE:{_first(notice.get('ND'))}",
            }
            # Only override the default (fetch time) when a real date is available,
            # so the 24h window does not treat old notices as freshly published.
            if published is not None:
                kwargs["published_at"] = published
            findings.append(RawFinding(**kwargs))
        return findings


class ZoningAgent(SourceAgent):
    """Widmungs- und Bauverfahren (Amtsblätter, Kundmachungen, UVP, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        return []


class DeveloperAgent(SourceAgent):
    """Immobilienentwickler (UBM, ARE, Soravia, Buwog, Value One, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        return []


class HotelAgent(SourceAgent):
    """Hotel- und Tourismusbereich (Tourismusverbände, Wirtschaftskammer, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        return []


class PressAgent(SourceAgent):
    """Presse & Fachportale (Immobilien Magazin, Der Standard, Leadersnet, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        return []


_AGENT_BY_TYPE: dict[SourceType, type[SourceAgent]] = {
    SourceType.TENDER: TenderAgent,
    SourceType.ZONING: ZoningAgent,
    SourceType.DEVELOPER: DeveloperAgent,
    SourceType.HOTEL: HotelAgent,
    SourceType.PRESS: PressAgent,
}


def build_agent(
    source: SourceConfig, config: Config, fixtures: FixtureProvider
) -> SourceAgent:
    agent_cls = _AGENT_BY_TYPE[source.type]
    return agent_cls(source, config, fixtures)


def build_agents(config: Config, fixtures: FixtureProvider) -> list[SourceAgent]:
    return [build_agent(s, config, fixtures) for s in config.enabled_sources]


def _parse_ted_date(value) -> datetime | None:
    """Parse a TED publication date (``PD``) into an aware UTC datetime.

    TED publishes dates as ``YYYYMMDD`` or ISO-8601; return None on anything else.
    """
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _first(value):
    """TED fields are often lists/dicts; return a plain string best-effort."""
    if value is None:
        return None
    if isinstance(value, list):
        return _first(value[0]) if value else None
    if isinstance(value, dict):
        for key in ("value", "text", "#text"):
            if key in value:
                return str(value[key])
        return None
    return str(value)
