from elk_lead_agent import scoring
from elk_lead_agent.models import RawFinding, SourceType


def _finding(**kw):
    base = dict(
        source_name="ANKÖ",
        source_type=SourceType.TENDER,
        title="Projekt",
        description="",
        status="Unbekannt",
    )
    base.update(kw)
    return RawFinding(**base)


def test_full_score(config):
    f = _finding(
        title="Mitarbeiterquartier in Holzmodulbau",
        status="Vor Einreichung",
        volume_eur=3_000_000,
        investor="UBM",
    )
    p = scoring.analyze(f, config)
    assert p.breakdown.volume_over_threshold == 20
    assert p.breakdown.timber_or_modular == 30
    assert p.breakdown.submission_imminent == 20
    assert p.breakdown.investor_known == 10
    assert p.breakdown.hotel_or_employee_housing == 20
    assert p.score == 100


def test_volume_threshold_is_strict(config):
    at = scoring.analyze(_finding(title="Budgethotel", volume_eur=2_000_000), config)
    over = scoring.analyze(_finding(title="Budgethotel", volume_eur=2_000_001), config)
    assert at.breakdown.volume_over_threshold == 0
    assert over.breakdown.volume_over_threshold == 20


def test_hotel_bonus_only_for_configured_categories(config):
    # Studentenheim is a target category but does NOT grant the hotel/employee bonus.
    p = scoring.analyze(_finding(title="Studentenwohnheim mit 200 Betten"), config)
    assert "studentenheime" in p.categories
    assert p.breakdown.hotel_or_employee_housing == 0


def test_irrelevant_finding(config):
    p = scoring.analyze(_finding(title="Sanierung Bürogebäude"), config)
    assert not scoring.is_relevant(p)


def test_investor_detected_from_text(config):
    p = scoring.analyze(_finding(title="Soravia baut Mitarbeiterquartier"), config)
    assert p.breakdown.investor_known == 10
