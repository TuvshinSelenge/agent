from elk_lead_agent import dedup, scoring
from elk_lead_agent.models import RawFinding, SourceType


def _project(title, url, volume=None, investor=None):
    f = RawFinding(
        source_name="X",
        source_type=SourceType.PRESS,
        title=title,
        url=url,
        volume_eur=volume,
        investor=investor,
    )
    from elk_lead_agent.config import load_config

    return scoring.analyze(f, load_config())


def test_dedupe_keeps_highest_score():
    strong = _project("Mitarbeiterquartier Holzbau", "http://x/1", volume=5_000_000, investor="UBM")
    weak = _project("Mitarbeiterquartier", "http://x/1")
    result = dedup.dedupe([weak, strong])
    assert len(result) == 1
    assert result[0].score == strong.score


def test_dedupe_distinct_urls_kept():
    a = _project("Boarding House", "http://x/1")
    b = _project("Boarding House", "http://x/2")
    assert len(dedup.dedupe([a, b])) == 2
