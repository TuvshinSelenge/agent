"""Within-run deduplication of scored projects."""

from __future__ import annotations

from .models import ScoredProject


def dedupe(projects: list[ScoredProject]) -> list[ScoredProject]:
    """Collapse duplicate fingerprints, keeping the highest-scoring instance.

    The same project can surface from multiple sources (e.g. a tender plus a
    press article). We keep the richest signal by preferring the higher score,
    then the more recent publication.
    """
    best: dict[str, ScoredProject] = {}
    for project in projects:
        fp = project.fingerprint
        current = best.get(fp)
        if current is None:
            best[fp] = project
            continue
        if project.score > current.score or (
            project.score == current.score
            and project.finding.published_at > current.finding.published_at
        ):
            best[fp] = project
    return list(best.values())
