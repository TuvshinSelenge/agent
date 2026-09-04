"""The research agent: uses an LLM to judge relevance and extract structured
projects from real fetched articles/notices — while keeping the real source URL.

Anti-hallucination: the model only chooses among candidates we actually fetched
(by index). It never invents URLs; the link on each result is the real link of
the selected candidate.
"""

from __future__ import annotations

from . import scoring
from .config import Config
from .llm import OpenAIClient
from .models import RawFinding, ScoredProject

MAX_CANDIDATES_PER_SOURCE = 30

_SYSTEM = (
    "Du bist ein Rechercheanalyst für ELK (Spezialist für Holz- und Modulbau). "
    "Du sichtest österreichische Immobilien-, Bau- und Vergabe-Meldungen und "
    "identifizierst ausschließlich konkrete PROJEKTE (Neubau/Umbau/Ausschreibung/"
    "Planung) in diesen Kategorien für temporäres bzw. Mitarbeiter-Wohnen und "
    "Beherbergung. Reine Marktkommentare, Politik, Personalien oder nicht "
    "einschlägige Themen sind NICHT relevant. Antworte ausschließlich mit JSON."
)


def _categories_block(config: Config) -> str:
    lines = []
    for key, cat in config.categories.items():
        kws = ", ".join(cat.keywords[:6])
        lines.append(f'- "{key}": {cat.label} (z. B. {kws})')
    return "\n".join(lines)


def _build_user_prompt(config: Config, candidates: list[RawFinding]) -> str:
    cat_block = _categories_block(config)
    items = []
    for i, f in enumerate(candidates):
        snippet = (f.description or "").strip().replace("\n", " ")
        items.append(f"[{i}] TITEL: {f.title}\n     TEXT: {snippet[:400]}")
    items_block = "\n".join(items)
    return f"""Zielkategorien (Schlüssel: Bedeutung):
{cat_block}

Bewertungssignale, die du je Projekt einschätzt:
- timber_or_modular: Wird Holzbau/Holz-Modulbau/Modulbau/serielles Bauen erwähnt?
- submission_imminent: Steht eine Einreichung/Baueinreichung/Bauverhandlung bevor?
- investor: bekannter Investor/Entwickler/Bauträger (Name) oder null
- volume_eur: geschätztes Projektvolumen in EUR als Zahl oder null
- location: Ort/Bundesland in Österreich (oder "Österreich")
- status: kurzer Projektstand (z. B. "In Planung", "Ausschreibung", "Vor Einreichung", "Bericht")

Kandidaten (jeweils mit Index):
{items_block}

Aufgabe: Gib die relevanten Projekte als JSON zurück. Nur Kandidaten, die
tatsächlich ein einschlägiges Projekt beschreiben. Format:
{{"projects": [{{"index": <int>, "categories": ["<schlüssel>", ...],
  "location": "<ort>", "status": "<status>", "volume_eur": <zahl|null>,
  "investor": "<name|null>", "timber_or_modular": <bool>,
  "submission_imminent": <bool>}}]}}
Wenn nichts passt: {{"projects": []}}. Verwende ausschließlich die oben
gelisteten Kategorie-Schlüssel."""


def extract_from_findings(
    findings: list[RawFinding],
    config: Config,
    client: OpenAIClient,
) -> list[ScoredProject]:
    """Have the LLM select & structure relevant projects from fetched candidates."""
    candidates = findings[:MAX_CANDIDATES_PER_SOURCE]
    if not candidates:
        return []
    data = client.complete_json(_SYSTEM, _build_user_prompt(config, candidates))
    results: list[ScoredProject] = []
    for proj in data.get("projects", []):
        try:
            idx = int(proj.get("index"))
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(candidates)):
            continue  # ignore hallucinated indices -> link stays real
        finding = candidates[idx]
        project = scoring.analyze_structured(finding, proj, config)
        if project.categories:  # keep only genuinely categorized projects
            results.append(project)
    return results


def extract_all(
    findings_by_source: dict[str, list[RawFinding]],
    config: Config,
    client: OpenAIClient,
) -> tuple[list[ScoredProject], list[str]]:
    """Run extraction per source; returns (projects, errors)."""
    projects: list[ScoredProject] = []
    errors: list[str] = []
    for source, findings in findings_by_source.items():
        try:
            projects.extend(extract_from_findings(findings, config, client))
        except Exception as exc:  # noqa: BLE001 - one bad source must not sink the run
            errors.append(f"{source} (LLM): {exc}")
    return projects, errors
