"""The analyst agent: categorization + scoring of a raw finding.

Implements the Bewertungssystem from the brief exactly:

    Projektvolumen > 2 Mio. EUR      -> +20
    Holz- oder Modulbau erwaehnt     -> +30
    Einreichung steht bevor          -> +20
    Investor bekannt                 -> +10
    Hotel / Mitarbeiterquartier      -> +20

    >= 60 Punkte -> Lead fuer Vertrieb.
"""

from __future__ import annotations

from . import matching
from .config import Config
from .models import RawFinding, ScoreBreakdown, ScoredProject


def detect_investor(finding: RawFinding, config: Config) -> str | None:
    """Return a known investor/developer name if one can be identified."""
    if finding.investor:
        return finding.investor
    text = finding.text
    for name in config.developers:
        if matching.matched_terms(text, [name]):
            return name
    # A developer-sourced finding implies a known investor (the developer itself).
    return None


def analyze(finding: RawFinding, config: Config) -> ScoredProject:
    """Categorize and score a single finding into a :class:`ScoredProject`."""
    text = finding.text
    keys, labels = matching.find_categories(text, config)

    is_timber = matching.mentions_timber_or_modular(text, config)
    is_submission = matching.submission_imminent(text, config)
    investor = detect_investor(finding, config)
    has_volume = finding.volume_eur is not None and finding.volume_eur > config.volume_threshold_eur
    is_hotel_or_employee = any(k in config.hotel_or_employee_categories for k in keys)

    pts = config.points
    breakdown = ScoreBreakdown(
        volume_over_threshold=pts.get("volume_over_threshold", 0) if has_volume else 0,
        timber_or_modular=pts.get("timber_or_modular", 0) if is_timber else 0,
        submission_imminent=pts.get("submission_imminent", 0) if is_submission else 0,
        investor_known=pts.get("investor_known", 0) if investor else 0,
        hotel_or_employee_housing=pts.get("hotel_or_employee_housing", 0)
        if is_hotel_or_employee
        else 0,
    )

    project = ScoredProject(
        finding=finding,
        fingerprint=finding.fingerprint,
        categories=keys,
        category_labels=labels,
        breakdown=breakdown,
        is_timber_or_modular=is_timber,
        contact=finding.contact,
    )
    # Stash the resolved investor back onto the finding for downstream enrichment.
    if investor and not finding.investor:
        project.finding.investor = investor
    return project


def is_relevant(project: ScoredProject) -> bool:
    """A finding is relevant if it maps to at least one target category."""
    return bool(project.categories)
