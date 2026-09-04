"""Tool-using research agent.

Instead of hard-wired parsers, the LLM is given two tools — ``web_search`` and
``fetch_url`` — and told to look through the public Austrian sources for concrete
projects in the target categories. It reads results, follows promising links, and
finally returns structured projects.

Anti-hallucination: the agent may only report a project whose source URL it
actually encountered via a tool (tracked in ``seen_urls``); anything else is
dropped, so every "Link zur Quelle" is real and resolvable.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from html.parser import HTMLParser

import httpx

from . import scoring
from .config import Config
from .llm import OpenAIClient
from .models import RawFinding, ScoredProject, SourceType

_UA = "Mozilla/5.0 (compatible; ELK-Lead-Agent/0.1)"
_HTTP_TIMEOUT = 20.0
_MAX_TEXT = 3500
_MAX_LINKS = 40
_MAX_ITERATIONS = 8


# --------------------------------------------------------------------------- #
# HTML helpers
# --------------------------------------------------------------------------- #
class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = urllib.parse.urljoin(self.base_url, href)
                self._anchor = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href:
            text = " ".join(" ".join(self._anchor).split())
            if text and self._href.startswith("http"):
                self.links.append((text[:120], self._href))
            self._href = None
            self._anchor = []

    def handle_data(self, data):
        if self._skip:
            return
        s = data.strip()
        if s:
            self.text_parts.append(s)
            if self._href is not None:
                self._anchor.append(s)


def _parse_html(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    p = _Extractor(base_url)
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    text = " ".join(p.text_parts)
    text = re.sub(r"\s+", " ", text)[:_MAX_TEXT]
    # de-duplicate links, keep order
    seen = set()
    links = []
    for t, u in p.links:
        if u not in seen:
            seen.add(u)
            links.append((t, u))
    return text, links[:_MAX_LINKS]


def _ddg_search(query: str, limit: int = 8) -> list[dict]:
    """Very small DuckDuckGo HTML scraper -> [{title, url}]."""
    resp = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": _UA},
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    _text, links = _parse_html(resp.text, "https://duckduckgo.com/")
    results: list[dict] = []
    seen = set()
    for title, url in links:
        real = url
        parsed = urllib.parse.urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                real = urllib.parse.unquote(qs["uddg"][0])
        if "duckduckgo.com" in urllib.parse.urlparse(real).netloc:
            continue
        if real in seen:
            continue
        seen.add(real)
        results.append({"title": title, "url": real})
        if len(results) >= limit:
            break
    return results


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Websuche (DuckDuckGo). Nutze site:-Filter für gezielte Quellen.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Lädt eine Seite und gibt Text + gefundene Links zurück.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]


class _ToolRunner:
    def __init__(self):
        self.seen_urls: set[str] = set()

    def run(self, name: str, args: dict) -> str:
        try:
            if name == "web_search":
                results = _ddg_search(str(args.get("query", "")))
                for r in results:
                    self.seen_urls.add(r["url"])
                return json.dumps({"results": results}, ensure_ascii=False)
            if name == "fetch_url":
                url = str(args.get("url", ""))
                resp = httpx.get(
                    url, headers={"User-Agent": _UA}, timeout=_HTTP_TIMEOUT, follow_redirects=True
                )
                self.seen_urls.add(str(resp.url))
                self.seen_urls.add(url)
                text, links = _parse_html(resp.text, str(resp.url))
                for _t, u in links:
                    self.seen_urls.add(u)
                return json.dumps(
                    {"url": str(resp.url), "text": text, "links": links}, ensure_ascii=False
                )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        return json.dumps({"error": f"unknown tool {name}"})


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def _system_prompt(config: Config) -> str:
    cats = "\n".join(
        f'- "{k}": {c.label} (z. B. {", ".join(c.keywords[:6])})'
        for k, c in config.categories.items()
    )
    sources = (
        "Behörden/Vergabe (ANKÖ, auftrag.at, TED ted.europa.eu, Bundesbeschaffung bbg.gv.at, "
        "Landesvergabeportale); Widmung/Bau (Amtsblätter, Gemeinde-Kundmachungen, Bauverhandlungen, "
        "Flächenwidmung, UVP uvp.gv.at); Entwickler (ubm-development.com, are.at, soravia.at, "
        "haring.at, buwog.com, value-one.com); Hotel/Tourismus (Tourismusverbände, wko.at, Fachmedien); "
        "Presse (immobilien-magazin.at, derstandard.at/immobilien, gewinn.com, leadersnet.at, kommunalnet.at)"
    )
    terms = ", ".join(config.search_terms)
    return (
        "Du bist ein Rechercheagent für ELK (Holz-/Modulbau). Ziel: NEUE konkrete "
        "Bauprojekte in Österreich in diesen Kategorien finden:\n"
        f"{cats}\n\n"
        f"Durchsuche öffentliche Quellen wie: {sources}.\n"
        f"Nutze Suchbegriffe wie: {terms}.\n\n"
        "Vorgehen: Nutze web_search (gern mit site:-Filter, z. B. "
        "'site:derstandard.at Boarding House') und fetch_url, um konkrete "
        "Projektmeldungen zu finden und zu öffnen. Sammle nur ECHTE Projekte "
        "(kein Marktkommentar, keine Politik). Für jedes Projekt merke dir die "
        "echte Quell-URL, die du tatsächlich geöffnet/gesehen hast.\n"
        "Wenn du genug hast (oder nichts findest), beende die Tool-Nutzung."
    )


_FINAL_INSTRUCTION = (
    "Gib jetzt die gefundenen Projekte als JSON zurück. Verwende NUR URLs, die du "
    "über die Tools tatsächlich gesehen hast. Format: {\"projects\":[{\"title\":..., "
    "\"url\":..., \"location\":..., \"status\":..., \"categories\":[\"<schlüssel>\"...], "
    "\"volume_eur\": <zahl|null>, \"investor\": <str|null>, "
    "\"timber_or_modular\": <bool>, \"submission_imminent\": <bool>}]}. "
    "Wenn nichts Passendes gefunden wurde: {\"projects\":[]}."
)


def run_agent(
    config: Config,
    client: OpenAIClient,
    max_iterations: int = _MAX_ITERATIONS,
) -> tuple[list[ScoredProject], list[str]]:
    """Run the tool-using browsing agent and return (projects, errors)."""
    errors: list[str] = []
    runner = _ToolRunner()
    messages: list[dict] = [
        {"role": "system", "content": _system_prompt(config)},
        {
            "role": "user",
            "content": "Finde aktuelle relevante Projekte in Österreich. "
            "Beginne mit gezielten Suchen zu den Kategorien/Quellen.",
        },
    ]

    for _ in range(max_iterations):
        try:
            msg = client.chat(messages, tools=_TOOLS)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Agent-Loop: {exc}")
            break
        tool_calls = msg.get("tool_calls") or []
        assistant_msg: dict = {"role": "assistant", "content": msg.get("content") or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls  # only when non-empty (API rejects [])
        messages.append(assistant_msg)
        if not tool_calls:
            break
        for call in tool_calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = runner.run(fn.get("name", ""), args)
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id"), "content": result[:6000]}
            )

    # Final structured extraction (no tools).
    messages.append({"role": "user", "content": _FINAL_INSTRUCTION})
    try:
        data = client.chat_json(messages)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Agent-Ergebnis: {exc}")
        return [], errors

    projects: list[ScoredProject] = []
    for proj in data.get("projects", []):
        url = str(proj.get("url", "")).strip()
        if not url or url not in runner.seen_urls:
            continue  # only real, actually-seen links
        finding = RawFinding(
            source_name=_source_label(url),
            source_type=SourceType.PRESS,
            title=str(proj.get("title") or "Projekt"),
            description=str(proj.get("title") or ""),
            url=url,
        )
        project = scoring.analyze_structured(finding, proj, config)
        if project.categories:
            projects.append(project)
    return projects, errors


def _source_label(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    return host or "Web"
