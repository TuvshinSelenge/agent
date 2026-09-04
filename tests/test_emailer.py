import pytest

from elk_lead_agent import emailer, scoring
from elk_lead_agent.emailer import (
    EmailNotConfiguredError,
    EmailSettings,
    build_message,
    send_report_email,
)
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


def test_settings_from_env():
    env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_FROM": "bot@example.com",
        "SMTP_STARTTLS": "false",
        "SMTP_TO": "a@x.com, b@x.com",
    }
    s = EmailSettings.from_env(env)
    assert s.is_configured
    assert s.port == 465
    assert s.use_tls is False
    assert s.recipients == ("a@x.com", "b@x.com")


def test_build_message_has_html_and_attachment(config):
    settings = EmailSettings(host="h", sender="bot@example.com")
    msg = build_message(_report(config), config, settings)

    assert msg["To"] == "selenge.tuvshin.stud@elkkampa.com"
    assert "Morgenreport" in msg["Subject"]

    # multipart with a text/html alternative + a text/html attachment
    payloads = list(msg.walk())
    assert any(part.get_content_type() == "text/html" for part in payloads)
    attachments = [p for p in payloads if p.get_filename()]
    assert attachments and attachments[0].get_filename() == "report_latest.html"
    assert b"Neue Projekte" in attachments[0].get_payload(decode=True)


def test_email_contains_link_when_public_url_set(config, monkeypatch):
    monkeypatch.setenv("REPORT_PUBLIC_URL", "https://reports.example.com")
    html = emailer.render_email_html(_report(config), config)
    assert "https://reports.example.com/report_latest.html" in html
    assert "HTML-Report öffnen" in html


def test_email_notes_attachment_without_link(config, monkeypatch):
    monkeypatch.delenv("REPORT_PUBLIC_URL", raising=False)
    html = emailer.render_email_html(_report(config), config)
    assert "als HTML-Datei bei" in html


def test_send_with_injected_transport(config):
    captured = []
    settings = EmailSettings(host="h", sender="bot@example.com")
    msg = send_report_email(
        _report(config), config, settings=settings, transport=lambda m, s: captured.append(m)
    )
    assert captured and captured[0] is msg


def test_send_raises_without_config(config):
    with pytest.raises(EmailNotConfiguredError):
        send_report_email(_report(config), config, settings=EmailSettings())
