"""Concrete collector agents, one class per source group, plus a factory.

Only TED ships a best-effort live fetcher (it exposes a public search API). The
other collectors fall back to bundled fixtures, which keeps the demonstration
deterministic while leaving a clean extension point for real integrations.
"""

from __future__ import annotations

from datetime import UTC, datetime

import feedparser
import httpx

from ..config import Config, SourceConfig
from ..models import RawFinding, SourceType
from .base import SourceAgent
from .fixtures import FixtureProvider

TED_API_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_TIMEOUT_S = 15.0
HTTP_TIMEOUT_S = 15.0
_USER_AGENT = "ELK-Lead-Agent/0.1 (+https://github.com/TuvshinSelenge/agent)"


class TenderAgent(SourceAgent):
    """Behörden & Vergabeplattformen (ANKÖ, Auftrag.at, TED, Bundesbeschaffung, ...)."""

    def fetch_live(self) -> list[RawFinding]:
        if self.source.name.startswith("TED"):
            return self._fetch_ted()
        return []

    def _fetch_ted(self) -> list[RawFinding]:
        # TED expert search: Austria + our free-text search terms.
        terms = " OR ".join(f'"{t}"' for t in self.config.search_terms)
        query = f"CY=AUT AND FT=({terms})"
        payload = {
            "query": query,
            "fields": ["ND", "TI", "PD", "links", "place-of-performance"],
            "limit": 50,
            "scope": "ALL",
        }
        headers = {"User-Agent": _USER_AGENT}
        with httpx.Client(timeout=TED_TIMEOUT_S, headers=headers) as client:
            resp = client.post(TED_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        findings: list[RawFinding] = []
        for notice in data.get("notices", []):
            nd = notice.get("publication-number") or notice.get("ND")
            title = _pick_lang(notice.get("TI")) or "TED-Ausschreibung"
            url = _ted_link(notice.get("links"), nd)
            if not url:
                continue
            kwargs = {
                "source_name": self.source.name,
                "source_type": SourceType.TENDER,
                "title": title,
                "description": title,
                "location": _ted_location(notice.get("place-of-performance")),
                "status": "EU-Ausschreibung",
                "url": url,
            }
            published = _parse_ted_date(notice.get("PD"))
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
    """Presse & Fachportale – liest echte Artikel aus dem konfigurierten RSS-Feed."""

    def fetch_live(self) -> list[RawFinding]:
        feed_url = self.source.feed
        if not feed_url:
            return []
        resp = httpx.get(feed_url, timeout=HTTP_TIMEOUT_S, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        findings: list[RawFinding] = []
        for entry in parsed.entries:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not link or not title:
                continue
            summary = getattr(entry, "summary", "") or ""
            kwargs = {
                "source_name": self.source.name,
                "source_type": SourceType.PRESS,
                "title": title,
                "description": summary,
                "location": "Österreich",
                "status": "Fachartikel",
                "url": link,
            }
            published = _parse_feed_date(entry)
            if published is not None:
                kwargs["published_at"] = published
            findings.append(RawFinding(**kwargs))
        return findings


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
    """Parse a TED publication date (``PD``) like ``2026-09-04+02:00`` (aware UTC)."""
    if not value:
        return None
    text = str(value).strip()[:10]  # keep the date portion, drop any tz offset
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _pick_lang(titles) -> str | None:
    """TED titles come as a {lang: text} dict; prefer German, then English."""
    if isinstance(titles, str):
        return titles
    if isinstance(titles, dict):
        for key in ("deu", "ger", "eng"):
            if titles.get(key):
                return str(titles[key])
        for v in titles.values():
            if v:
                return str(v)
    return None


def _ted_link(links, nd) -> str | None:
    """Return a real, working ted.europa.eu URL for the notice."""
    if isinstance(links, dict):
        pdf = links.get("pdf") or {}
        for key in ("DEU", "ENG"):
            if pdf.get(key):
                return str(pdf[key])
        if isinstance(pdf, dict) and pdf:
            return str(next(iter(pdf.values())))
        xml = links.get("xml") or {}
        if isinstance(xml, dict) and xml:
            return str(next(iter(xml.values())))
    if nd:
        return f"https://ted.europa.eu/de/notice/{nd}"
    return None


def _ted_location(pop) -> str:
    if isinstance(pop, list) and pop:
        return "Österreich" if "AUT" in pop else str(pop[0])
    return "Österreich"


def _parse_feed_date(entry) -> datetime | None:
    """Convert a feedparser entry's parsed date to an aware UTC datetime.

    feedparser's ``*_parsed`` struct_time is in UTC, so use ``calendar.timegm``.
    """
    import calendar

    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            return datetime.fromtimestamp(calendar.timegm(st), tz=UTC)
    return None
