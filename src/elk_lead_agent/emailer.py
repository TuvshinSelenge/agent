"""E-mail delivery of the morning report.

Sends a nicely formatted HTML e-mail that contains:

* a prominent "Report öffnen" button/link to the hosted HTML report
  (``email.public_base_url`` + ``report_filename``), and
* the full standalone HTML report as an attachment, so a click always opens
  the nicely designed page even when no hosting is configured yet.

SMTP credentials are read from environment variables / secrets and never stored
in the repository:

    SMTP_HOST, SMTP_PORT (default 587), SMTP_USERNAME, SMTP_PASSWORD,
    SMTP_FROM (sender), SMTP_STARTTLS (default true), SMTP_TO (optional override).
"""

from __future__ import annotations

import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage

from jinja2 import Template

from .config import Config
from .models import Potential, RunReport
from .report import _fmt_dt, _volume_label, to_html


class EmailNotConfiguredError(RuntimeError):
    """Raised when SMTP settings or recipients are missing."""


@dataclass
class EmailSettings:
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    sender: str | None = None
    use_tls: bool = True
    recipients: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> EmailSettings:
        env = env if env is not None else dict(os.environ)
        to = env.get("SMTP_TO", "")
        recipients = tuple(r.strip() for r in to.split(",") if r.strip())
        return cls(
            host=env.get("SMTP_HOST"),
            port=int(env.get("SMTP_PORT", "587")),
            username=env.get("SMTP_USERNAME"),
            password=env.get("SMTP_PASSWORD"),
            sender=env.get("SMTP_FROM") or env.get("SMTP_USERNAME"),
            use_tls=env.get("SMTP_STARTTLS", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            recipients=recipients,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.sender)


# Transport signature: (message, settings) -> None
Transport = Callable[[EmailMessage, EmailSettings], None]

_BADGE = {
    Potential.HOCH: ("#0a5", "#cdeccd"),
    Potential.MITTEL: ("#8a6d00", "#fdf3c4"),
    Potential.NIEDRIG: ("#666", "#eeeeee"),
}


def _report_link(config: Config) -> str | None:
    # An explicit env override wins (handy when serving reports on the fly).
    base = (os.getenv("REPORT_PUBLIC_URL") or config.email.public_base_url or "").strip()
    if not base:
        return None
    return f"{base.rstrip('/')}/{config.email.report_filename}"


_EMAIL_TEMPLATE = Template(
    """<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     max-width:720px;margin:0 auto;color:#1a1a1a;">
  <div style="background:#0b5;color:#fff;padding:18px 22px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:20px;">ELK Lead Agent · Morgenreport</h1>
    <div style="opacity:.9;font-size:13px;margin-top:4px;">
      Neue Projekte der letzten {{ r.window_hours }} Stunden · Stand {{ generated }}
    </div>
  </div>
  <div style="border:1px solid #e2e2e2;border-top:none;padding:22px;border-radius:0 0 8px 8px;">
    <p style="font-size:15px;margin-top:0;">
      <strong>{{ r.projects|length }}</strong> neue Projekte,
      davon <strong style="color:#0a5;">{{ r.leads|length }} Leads</strong>
      (ab {{ r.threshold_lead }} Punkten) aus {{ r.sources_queried|length }} Quellen.
    </p>

    {% if link %}
    <p style="margin:22px 0;">
      <a href="{{ link }}"
         style="background:#0b5;color:#fff;text-decoration:none;padding:12px 22px;
                border-radius:6px;font-weight:600;display:inline-block;">
        📄 HTML-Report öffnen
      </a>
    </p>
    {% else %}
    <p style="font-size:13px;color:#666;margin:18px 0;">
      Der vollständige, formatierte Report liegt dieser E-Mail als HTML-Datei bei
      (einfach öffnen). Sobald eine öffentliche Report-URL konfiguriert ist,
      erscheint hier zusätzlich ein direkter Link.
    </p>
    {% endif %}

    <table style="border-collapse:collapse;width:100%;font-size:13px;margin-top:8px;">
      <thead>
        <tr>
          <th style="text-align:left;background:#0b5;color:#fff;padding:8px;">Projekt</th>
          <th style="text-align:left;background:#0b5;color:#fff;padding:8px;">Ort</th>
          <th style="text-align:left;background:#0b5;color:#fff;padding:8px;">Status</th>
          <th style="text-align:right;background:#0b5;color:#fff;padding:8px;">Score</th>
          <th style="text-align:left;background:#0b5;color:#fff;padding:8px;">Potenzial</th>
          <th style="text-align:left;background:#0b5;color:#fff;padding:8px;">ELK</th>
        </tr>
      </thead>
      <tbody>
      {% for p in rows %}
        <tr style="background:{{ '#f6f6f6' if loop.index0 % 2 else '#fff' }};">
          <td style="padding:8px;border:1px solid #eee;">{{ p.finding.title }}</td>
          <td style="padding:8px;border:1px solid #eee;">{{ p.finding.location }}</td>
          <td style="padding:8px;border:1px solid #eee;">{{ p.finding.status }}</td>
          <td style="padding:8px;border:1px solid #eee;text-align:right;font-weight:600;">{{ p.score }}</td>
          <td style="padding:8px;border:1px solid #eee;">
            <span style="{{ badge(p.potential) }}">{{ p.potential.value }}</span></td>
          <td style="padding:8px;border:1px solid #eee;">
            <span style="{{ badge(p.elk_relevance) }}">{{ p.elk_relevance.value }}</span></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    {% if r.leads %}
    <h2 style="font-size:16px;margin-top:26px;">Top-Leads für den Vertrieb</h2>
    {% for p in r.leads[:5] %}
      <div style="border:1px solid #cdeccd;border-left:5px solid #0b5;padding:12px 14px;
                  margin:10px 0;border-radius:4px;">
        <div style="font-weight:700;">{{ p.finding.title }} — {{ p.finding.location }}</div>
        <div style="font-size:13px;color:#333;margin-top:6px;">
          <div>Projektstand: {{ p.finding.status }} · Score {{ p.score }}</div>
          <div>Geschätztes Volumen: {{ volume(p) }} · ELK-Relevanz: {{ p.elk_relevance.value }}</div>
          <div>Ansprechpartner: {{ p.contact or '-' }}</div>
          {% if p.finding.url %}<div>Quelle: <a href="{{ p.finding.url }}">{{ p.finding.url }}</a></div>{% endif %}
          <div style="margin-top:4px;"><em>Nächste Aktion: {{ p.next_action }}</em></div>
        </div>
      </div>
    {% endfor %}
    {% endif %}

    <p style="font-size:12px;color:#999;margin-top:24px;">
      Automatisch erzeugt vom ELK Lead Agent.
    </p>
  </div>
</div>
"""
)


def _badge_style(p: Potential) -> str:
    fg, bg = _BADGE[p]
    return (
        f"background:{bg};color:{fg};padding:2px 8px;border-radius:8px;font-size:12px;"
    )


def render_email_html(report: RunReport, config: Config) -> str:
    """Render the inline-styled HTML used as the e-mail body."""
    rows = report.projects[:15]
    return _EMAIL_TEMPLATE.render(
        r=report,
        rows=rows,
        generated=_fmt_dt(report.generated_at),
        link=_report_link(config),
        badge=_badge_style,
        volume=_volume_label,
    )


def _plain_text(report: RunReport, config: Config) -> str:
    lines = [
        "ELK Lead Agent - Morgenreport",
        f"Neue Projekte der letzten {report.window_hours} Stunden (Stand {_fmt_dt(report.generated_at)})",
        f"{len(report.projects)} Projekte, {len(report.leads)} Leads (ab {report.threshold_lead} Punkten).",
        "",
    ]
    link = _report_link(config)
    if link:
        lines += [f"HTML-Report: {link}", ""]
    else:
        lines += ["Der vollstaendige HTML-Report liegt als Anhang bei.", ""]
    for p in report.leads:
        lines.append(f"- [{p.score}] {p.finding.title} ({p.finding.location}) -> {p.next_action}")
    return "\n".join(lines)


def build_message(
    report: RunReport,
    config: Config,
    settings: EmailSettings,
    *,
    attachment_html: str | None = None,
) -> EmailMessage:
    """Build a multipart e-mail (plain + HTML) with the report attached."""
    recipients = settings.recipients or config.email.recipients
    if not recipients:
        raise EmailNotConfiguredError("Keine Empfänger konfiguriert (email.recipients / SMTP_TO).")

    n_leads = len(report.leads)
    date = report.generated_at.strftime("%Y-%m-%d")

    msg = EmailMessage()
    msg["Subject"] = f"{config.email.subject_prefix} Morgenreport {date} – {n_leads} Leads"
    msg["From"] = settings.sender or "elk-lead-agent@localhost"
    msg["To"] = ", ".join(recipients)

    msg.set_content(_plain_text(report, config))
    msg.add_alternative(render_email_html(report, config), subtype="html")

    html = attachment_html if attachment_html is not None else to_html(report)
    msg.add_attachment(
        html.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename=config.email.report_filename,
    )
    return msg


def _smtp_transport(message: EmailMessage, settings: EmailSettings) -> None:  # pragma: no cover
    with smtplib.SMTP(settings.host, settings.port, timeout=30) as smtp:
        smtp.ehlo()
        if settings.use_tls:
            smtp.starttls()
            smtp.ehlo()
        if settings.username and settings.password:
            smtp.login(settings.username, settings.password)
        smtp.send_message(message)


def send_report_email(
    report: RunReport,
    config: Config,
    *,
    settings: EmailSettings | None = None,
    attachment_html: str | None = None,
    transport: Transport | None = None,
) -> EmailMessage:
    """Compose and send the report e-mail. Returns the sent message.

    ``transport`` can be injected for testing; by default a real SMTP connection
    is used. Raises :class:`EmailNotConfiguredError` if SMTP is not set up.
    """
    settings = settings or EmailSettings.from_env()
    if transport is None and not settings.is_configured:
        raise EmailNotConfiguredError(
            "SMTP ist nicht konfiguriert. Bitte SMTP_HOST und SMTP_FROM (sowie ggf. "
            "SMTP_USERNAME/SMTP_PASSWORD) als Secrets setzen."
        )
    message = build_message(report, config, settings, attachment_html=attachment_html)
    (transport or _smtp_transport)(message, settings)
    return message
