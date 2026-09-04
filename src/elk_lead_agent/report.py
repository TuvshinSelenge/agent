"""The reporting agent: renders the morning report in several formats."""

from __future__ import annotations

from datetime import datetime

from jinja2 import Environment
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Potential, RunReport, ScoredProject

_POTENTIAL_STYLE = {
    Potential.HOCH: "bold green",
    Potential.MITTEL: "yellow",
    Potential.NIEDRIG: "dim",
}


def _fmt_eur(value: float | None) -> str:
    if value is None:
        return "k. A."
    # German-style thousands separator.
    return f"{value:,.0f}".replace(",", ".") + " €"


def _volume_label(project: ScoredProject) -> str:
    val = _fmt_eur(project.volume_estimate_eur)
    if project.finding.volume_eur is None and project.volume_estimate_eur is not None:
        return f"≈ {val} (geschätzt)"
    return val


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------- #
# Console
# --------------------------------------------------------------------------- #
def render_console(report: RunReport, console: Console | None = None) -> None:
    console = console or Console()
    leads = report.leads
    header = (
        f"[bold]Neue Projekte der letzten {report.window_hours} Stunden[/bold]\n"
        f"Stand: {_fmt_dt(report.generated_at)}  ·  "
        f"{len(report.projects)} Projekte  ·  "
        f"[bold green]{len(leads)} Leads[/bold green] (ab {report.threshold_lead} Punkten)  ·  "
        f"{len(report.sources_queried)} Quellen durchsucht"
    )
    console.print(Panel(header, title="ELK Lead Agent", expand=False))

    if not report.projects:
        console.print("[dim]Keine neuen relevanten Projekte in diesem Zeitfenster.[/dim]")
        return

    table = Table(show_lines=False, expand=True)
    table.add_column("Projekt", overflow="fold", ratio=3)
    table.add_column("Ort", ratio=1)
    table.add_column("Status", ratio=2)
    table.add_column("Score", justify="right")
    table.add_column("Potenzial")
    table.add_column("ELK-Relevanz")
    table.add_column("Lead", justify="center")

    for p in report.projects:
        table.add_row(
            p.finding.title,
            p.finding.location,
            p.finding.status,
            str(p.score),
            f"[{_POTENTIAL_STYLE[p.potential]}]{p.potential.value}[/]",
            f"[{_POTENTIAL_STYLE[p.elk_relevance]}]{p.elk_relevance.value}[/]",
            "[bold green]✓[/]" if p.is_lead else "",
        )
    console.print(table)

    if leads:
        console.print("\n[bold green]Lead-Details für den Vertrieb[/bold green]")
        for p in leads:
            console.print(_lead_panel(p))


def _lead_panel(p: ScoredProject) -> Panel:
    lines = [
        f"[bold]{p.finding.title}[/bold]  ·  {p.finding.location}",
        f"Projektstand:  {p.finding.status}",
        f"Kategorien:    {', '.join(p.category_labels) or '-'}",
        f"Score:         {p.score}  ({', '.join(p.breakdown.reasons())})",
        f"Volumen:       {_volume_label(p)}",
        f"Ansprechpartner: {p.contact or '-'}",
        f"ELK-Relevanz:  {p.elk_relevance.value}",
        f"Quelle:        {p.finding.url or '-'}",
        f"Nächste Aktion: [italic]{p.next_action}[/italic]",
    ]
    return Panel("\n".join(lines), border_style="green", expand=False)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def to_markdown(report: RunReport) -> str:
    lines: list[str] = []
    lines.append(f"# Neue Projekte der letzten {report.window_hours} Stunden")
    lines.append("")
    lines.append(
        f"*Stand: {_fmt_dt(report.generated_at)} · {len(report.projects)} Projekte · "
        f"{len(report.leads)} Leads (ab {report.threshold_lead} Punkten) · "
        f"{len(report.sources_queried)} Quellen durchsucht*"
    )
    lines.append("")
    lines.append("| Projekt | Ort | Status | Score | Potenzial | ELK-Relevanz | Lead |")
    lines.append("| --- | --- | --- | ---: | --- | --- | :---: |")
    for p in report.projects:
        lead = "✅" if p.is_lead else ""
        lines.append(
            f"| {p.finding.title} | {p.finding.location} | {p.finding.status} | "
            f"{p.score} | {p.potential.value} | {p.elk_relevance.value} | {lead} |"
        )
    lines.append("")

    if report.leads:
        lines.append("## Lead-Details für den Vertrieb")
        lines.append("")
        for p in report.leads:
            lines.append(f"### {p.finding.title} — {p.finding.location}")
            lines.append("")
            lines.append(f"- **Projektstand:** {p.finding.status}")
            lines.append(f"- **Kategorien:** {', '.join(p.category_labels) or '-'}")
            lines.append(
                f"- **Score:** {p.score} ({', '.join(p.breakdown.reasons())})"
            )
            lines.append(f"- **Geschätztes Volumen:** {_volume_label(p)}")
            lines.append(f"- **Ansprechpartner:** {p.contact or '-'}")
            lines.append(f"- **ELK-Relevanz:** {p.elk_relevance.value}")
            lines.append(f"- **Link zur Quelle:** {p.finding.url or '-'}")
            lines.append(f"- **Empfohlene nächste Aktion:** {p.next_action}")
            lines.append("")

    if report.errors:
        lines.append("## Hinweise")
        lines.append("")
        for err in report.errors:
            lines.append(f"- ⚠️ {err}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
# autoescape=True: source-controlled values (title, location, url, ...) are
# escaped, so a malicious title cannot inject markup/script into the report.
_JINJA = Environment(autoescape=True)
_HTML_TEMPLATE = _JINJA.from_string(
    """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>ELK Lead Agent – Morgenreport</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 2rem; color: #1a1a1a; }
  h1 { margin-bottom: .2rem; }
  .meta { color: #666; margin-bottom: 1.5rem; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
  th, td { border: 1px solid #ddd; padding: .5rem .6rem; text-align: left; font-size: .95rem; }
  th { background: #0b5; color: #fff; }
  tr:nth-child(even) { background: #f6f6f6; }
  .lead td { font-weight: 600; }
  .badge { padding: .1rem .5rem; border-radius: .5rem; font-size: .8rem; }
  .Hoch { background: #cdeccd; color: #0a5; }
  .Mittel { background: #fdf3c4; color: #8a6d00; }
  .Niedrig { background: #eee; color: #666; }
  .card { border: 1px solid #cdeccd; border-left: 5px solid #0b5; padding: .8rem 1rem; margin: .6rem 0; border-radius: .3rem; }
  .card h3 { margin: 0 0 .4rem; }
  .card ul { margin: 0; padding-left: 1.1rem; }
</style>
</head>
<body>
  <h1>Neue Projekte der letzten {{ r.window_hours }} Stunden</h1>
  <div class="meta">Stand: {{ generated }} · {{ r.projects|length }} Projekte ·
    {{ r.leads|length }} Leads (ab {{ r.threshold_lead }} Punkten) ·
    {{ r.sources_queried|length }} Quellen durchsucht</div>

  <table>
    <thead><tr>
      <th>Projekt</th><th>Ort</th><th>Status</th><th>Score</th>
      <th>Potenzial</th><th>ELK-Relevanz</th><th>Lead</th>
    </tr></thead>
    <tbody>
    {% for p in r.projects %}
      <tr class="{{ 'lead' if p.is_lead else '' }}">
        <td>{{ p.finding.title }}</td>
        <td>{{ p.finding.location }}</td>
        <td>{{ p.finding.status }}</td>
        <td style="text-align:right">{{ p.score }}</td>
        <td><span class="badge {{ p.potential.value }}">{{ p.potential.value }}</span></td>
        <td><span class="badge {{ p.elk_relevance.value }}">{{ p.elk_relevance.value }}</span></td>
        <td style="text-align:center">{{ '✅' if p.is_lead else '' }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  {% if r.leads %}
  <h2>Lead-Details für den Vertrieb</h2>
  {% for p in r.leads %}
    <div class="card">
      <h3>{{ p.finding.title }} — {{ p.finding.location }}</h3>
      <ul>
        <li><strong>Projektstand:</strong> {{ p.finding.status }}</li>
        <li><strong>Kategorien:</strong> {{ p.category_labels|join(', ') or '-' }}</li>
        <li><strong>Score:</strong> {{ p.score }} ({{ p.breakdown.reasons()|join(', ') }})</li>
        <li><strong>Geschätztes Volumen:</strong> {{ volume(p) }}</li>
        <li><strong>Ansprechpartner:</strong> {{ p.contact or '-' }}</li>
        <li><strong>ELK-Relevanz:</strong> {{ p.elk_relevance.value }}</li>
        <li><strong>Link zur Quelle:</strong>
          {% if p.finding.url %}<a href="{{ p.finding.url }}">{{ p.finding.url }}</a>{% else %}-{% endif %}</li>
        <li><strong>Empfohlene nächste Aktion:</strong> {{ p.next_action }}</li>
      </ul>
    </div>
  {% endfor %}
  {% endif %}
</body>
</html>
"""
)


def to_html(report: RunReport) -> str:
    return _HTML_TEMPLATE.render(
        r=report,
        generated=_fmt_dt(report.generated_at),
        volume=_volume_label,
    )


def to_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)
