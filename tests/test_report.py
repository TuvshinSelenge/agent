import json

from elk_lead_agent import report as report_mod
from elk_lead_agent import scoring
from elk_lead_agent.enrichment import enrich
from elk_lead_agent.models import RawFinding, RunReport, SourceType


def _report(config):
    f = RawFinding(
        source_name="ANKÖ",
        source_type=SourceType.TENDER,
        title="Mitarbeiterquartier Holzmodulbau",
        status="Vor Einreichung",
        url="http://example/lead",
        volume_eur=5_000_000,
        investor="UBM",
    )
    p = enrich(scoring.analyze(f, config), config)
    return RunReport(threshold_lead=config.threshold_lead, projects=[p], sources_queried=["ANKÖ"])


def test_markdown_contains_table_and_lead(config):
    md = report_mod.to_markdown(_report(config))
    assert "Neue Projekte der letzten" in md
    assert "| Projekt |" in md
    assert "Mitarbeiterquartier Holzmodulbau" in md
    assert "Empfohlene nächste Aktion" in md


def test_html_is_valid_document(config):
    html = report_mod.to_html(_report(config))
    assert html.startswith("<!doctype html>")
    assert "Mitarbeiterquartier Holzmodulbau" in html
    assert "ELK-Relevanz" in html


def test_json_roundtrip(config):
    data = json.loads(report_mod.to_json(_report(config)))
    assert data["threshold_lead"] == 60
    assert data["projects"][0]["is_lead"] is True


def test_console_renders(config):
    from rich.console import Console

    console = Console(file=open("/dev/null", "w"), force_terminal=False)
    report_mod.render_console(_report(config), console)


def test_html_escapes_source_controlled_values(config):
    f = RawFinding(
        source_name="ANKÖ",
        source_type=SourceType.TENDER,
        title="<script>alert('xss')</script> Mitarbeiterquartier Holzbau",
        status="Vor Einreichung",
        url="http://example/lead",
        volume_eur=5_000_000,
        investor="UBM",
    )
    p = enrich(scoring.analyze(f, config), config)
    report = RunReport(threshold_lead=config.threshold_lead, projects=[p])
    html = report_mod.to_html(report)
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;" in html
