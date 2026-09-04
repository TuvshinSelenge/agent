"""The enrichment agent: fills report-ready fields on a scored project.

Adds the columns required by the morning report that are not part of scoring:
Ansprechpartner, geschätztes Volumen, Potenzial, ELK-Relevanz und die
empfohlene nächste Aktion.
"""

from __future__ import annotations

from .config import Config
from .models import Potential, ScoredProject, SourceType

# Rough per-project volume estimates (EUR) by category, used only for display
# when a source does not publish a concrete figure. These never affect scoring.
_VOLUME_HINTS_EUR = {
    "budget_hotels": 8_000_000,
    "serviced_apartments": 9_000_000,
    "studentenheime": 6_500_000,
    "mitarbeiterquartiere": 3_800_000,
    "arbeiterunterkuenfte": 3_200_000,
    "wohnen_auf_zeit": 5_000_000,
    "gewerbliche_wohnanlagen": 4_500_000,
    "pflege_sozialwohnen": 4_000_000,
}


def _potential(score: int) -> Potential:
    if score >= 80:
        return Potential.HOCH
    if score >= 60:
        return Potential.MITTEL
    return Potential.NIEDRIG


def _elk_relevance(project: ScoredProject) -> Potential:
    if not project.categories:
        return Potential.NIEDRIG
    if project.is_timber_or_modular:
        return Potential.HOCH
    return Potential.MITTEL


def _resolve_contact(project: ScoredProject, config: Config) -> str | None:
    if project.contact:
        return project.contact
    investor = project.finding.investor
    if investor and investor in config.developers:
        return config.developers[investor]
    finding = project.finding
    if finding.source_type == SourceType.DEVELOPER:
        return f"{finding.source_name} – Projektentwicklung"
    if finding.source_type == SourceType.TENDER:
        return f"{finding.source_name} – Vergabestelle"
    if finding.source_type == SourceType.ZONING:
        return f"{finding.location} – Bauamt / Gemeinde"
    if finding.source_type == SourceType.HOTEL:
        return f"{finding.source_name} – Ansprechpartner Projekt"
    return f"{finding.source_name} – Redaktion"


def _estimate_volume(project: ScoredProject) -> float | None:
    if project.finding.volume_eur is not None:
        return project.finding.volume_eur
    for key in project.categories:
        if key in _VOLUME_HINTS_EUR:
            return float(_VOLUME_HINTS_EUR[key])
    return None


def _next_action(project: ScoredProject, is_lead: bool, config: Config) -> str:
    submission = project.breakdown.submission_imminent > 0
    contact = project.contact or "Projektträger"
    if is_lead and submission:
        return f"Sofort Kontakt aufnehmen ({contact}) – Angebot Holz-/Modulbau vorbereiten"
    if is_lead:
        return f"In Vertriebspipeline aufnehmen und {contact} kontaktieren"
    if submission:
        return "Kurzfristig beobachten – Einreichunterlagen anfragen"
    if not project.is_timber_or_modular:
        return "Beobachten und Holz-/Modulbau-Alternative aktiv einbringen"
    return "Beobachten"


def enrich(project: ScoredProject, config: Config) -> ScoredProject:
    """Populate the report-ready fields on ``project`` in place and return it."""
    score = project.score
    project.is_lead = score >= config.threshold_lead
    project.potential = _potential(score)
    project.elk_relevance = _elk_relevance(project)
    project.contact = _resolve_contact(project, config)
    project.volume_estimate_eur = _estimate_volume(project)
    project.next_action = _next_action(project, project.is_lead, config)
    return project
