from datetime import UTC, datetime

from helpers import write_fixtures

from elk_lead_agent.config import load_config
from elk_lead_agent.orchestrator import Orchestrator
from elk_lead_agent.sources import FixtureProvider
from elk_lead_agent.state import StateStore

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _entries():
    return [
        {  # lead: all criteria -> 100
            "source": "ANKÖ",
            "type": "tender",
            "title": "Mitarbeiterquartier in Holzmodulbau",
            "status": "Vor Einreichung",
            "url": "http://x/lead",
            "hours_ago": 2,
            "volume_eur": 5_000_000,
            "investor": "UBM",
        },
        {  # duplicate of the lead, weaker -> should be deduped away
            "source": "Immobilien Magazin",
            "type": "press",
            "title": "Bericht zum Mitarbeiterquartier",
            "status": "Bericht",
            "url": "http://x/lead",
            "hours_ago": 1,
        },
        {  # relevant but outside the 24h window -> filtered
            "source": "Leadersnet",
            "type": "press",
            "title": "Altes Studentenwohnheim",
            "url": "http://x/old",
            "hours_ago": 48,
        },
        {  # not relevant -> filtered
            "source": "Auftrag.at",
            "type": "tender",
            "title": "Sanierung Bürogebäude",
            "url": "http://x/office",
            "hours_ago": 1,
        },
    ]


def _orchestrator(tmp_path):
    fixtures = FixtureProvider(
        fixture_dir=write_fixtures(tmp_path / "fixtures", _entries()), now=NOW
    )
    return Orchestrator(
        config=load_config(),
        fixtures=fixtures,
        state=StateStore(enabled=False),
        now=NOW,
    )


def test_orchestrator_filters_and_scores(tmp_path):
    report = _orchestrator(tmp_path).run(persist_state=False)
    # office (irrelevant), old (window), and duplicate are all removed.
    assert len(report.projects) == 1
    project = report.projects[0]
    assert project.score == 100
    assert project.is_lead
    assert len(report.leads) == 1
    assert "ANKÖ" in report.sources_queried


def test_orchestrator_dedup_state_marks_seen(tmp_path):
    state_path = tmp_path / "seen.json"
    fixture_dir = write_fixtures(tmp_path / "fixtures", _entries())
    fixtures = FixtureProvider(fixture_dir=fixture_dir, now=NOW)
    orch = Orchestrator(
        config=load_config(),
        fixtures=fixtures,
        state=StateStore(path=state_path),
        now=NOW,
    )
    first = orch.run()
    assert len(first.projects) == 1

    # Second run with a fresh state store reading the same file: already seen.
    fixtures2 = FixtureProvider(fixture_dir=fixture_dir, now=NOW)
    orch2 = Orchestrator(
        config=load_config(),
        fixtures=fixtures2,
        state=StateStore(path=state_path),
        now=NOW,
    )
    second = orch2.run()
    assert len(second.projects) == 0
