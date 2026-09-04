"""Command-line interface for the ELK Lead Agent orchestrator."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from .config import load_config
from .orchestrator import Orchestrator
from .report import render_console, to_json, to_markdown
from .runner import write_outputs
from .state import StateStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elk-agent",
        description="Orchestrator + Agenten zur täglichen Lead-Identifikation "
        "(temporäres Wohnen / Beherbergung in Österreich).",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Einen Durchlauf ausführen und Report erzeugen.")
    run.add_argument("--config", default=None, help="Pfad zur config.yaml")
    run.add_argument(
        "--format",
        choices=["console", "markdown", "json"],
        default="console",
        help="Ausgabeformat auf stdout (Standard: console).",
    )
    run.add_argument(
        "--output-dir",
        default="output",
        help="Verzeichnis für Report-Dateien (md/html/json). Leer lassen zum Deaktivieren.",
    )
    run.add_argument(
        "--no-write", action="store_true", help="Keine Report-Dateien schreiben."
    )
    run.add_argument(
        "--no-state",
        action="store_true",
        help="Zustands-Speicher (Dedup über Läufe) deaktivieren.",
    )
    run.add_argument(
        "--reset-state",
        action="store_true",
        help="Zustands-Speicher vor dem Lauf zurücksetzen.",
    )
    run.add_argument(
        "--email",
        action="store_true",
        help="Report per E-Mail versenden (benötigt SMTP-Secrets).",
    )
    run.add_argument(
        "--to",
        default=None,
        help="Empfänger überschreiben (Komma-getrennt). Standard: config email.recipients.",
    )

    schedule = sub.add_parser("schedule", help="Täglich zur festen Uhrzeit laufen.")
    schedule.add_argument("--at", default="06:00", help="Uhrzeit HH:MM (Standard 06:00).")
    schedule.add_argument("--config", default=None)
    schedule.add_argument("--output-dir", default="output")
    schedule.add_argument("--email", action="store_true", help="Report täglich per E-Mail versenden.")
    schedule.add_argument("--to", default=None, help="Empfänger überschreiben (Komma-getrennt).")

    serve = sub.add_parser("serve", help="output/ als statische Website ausliefern (für Report-Links).")
    serve.add_argument("--dir", default="output", help="Zu servierendes Verzeichnis.")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    web = sub.add_parser(
        "web",
        help="Interaktive Web-UI mit Buttons zum Aktualisieren und On-Demand-Versand.",
    )
    web.add_argument("--host", default="0.0.0.0")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--output-dir", default="output")
    web.add_argument("--config", default=None)
    web.add_argument(
        "--token",
        default=None,
        help="Zugriffs-Token; sonst aus WEB_TOKEN. Schützt /run vor unbefugtem Auslösen.",
    )

    sub.add_parser("sources", help="Konfigurierte Quellen auflisten.")
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    console = Console()
    state = StateStore(enabled=not args.no_state)
    if args.reset_state:
        state.reset()

    orchestrator = Orchestrator(config=load_config(args.config), state=state)
    # Do not persist "seen" yet: only mark leads seen after delivery succeeds,
    # so a write/e-mail failure never silently drops them from future runs.
    report = orchestrator.run(persist_state=False)

    if args.format == "console":
        render_console(report, console)
    elif args.format == "markdown":
        print(to_markdown(report))
    elif args.format == "json":
        print(to_json(report))

    if not args.no_write and args.output_dir:
        paths = write_outputs(report, args.output_dir)
        if args.format == "console":
            console.print(
                f"\n[dim]Report gespeichert: {paths['latest_markdown']} · "
                f"{paths['latest_html']}[/dim]"
            )

    email_rc = 0
    if args.email:
        email_rc = _send_email(report, orchestrator.config, console, args.to)
        if email_rc != 0:
            # Delivery failed: leave state untouched so these leads reappear next run.
            return email_rc

    if not args.no_state:
        orchestrator.commit_seen(report)
    return email_rc


def _send_email(report, config, console: Console, to: str | None) -> int:
    from .emailer import EmailNotConfiguredError, EmailSettings, send_report_email

    settings = EmailSettings.from_env()
    if to:
        settings.recipients = tuple(r.strip() for r in to.split(",") if r.strip())
    try:
        msg = send_report_email(report, config, settings=settings)
    except EmailNotConfiguredError as exc:
        console.print(f"[red]E-Mail nicht gesendet:[/red] {exc}")
        return 3
    except OSError as exc:
        console.print(f"[red]E-Mail-Versand fehlgeschlagen:[/red] {exc}")
        return 4
    console.print(f"[green]Report per E-Mail gesendet an:[/green] {msg['To']}")
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    from .scheduler import run_daily

    try:
        hour, minute = (int(x) for x in args.at.split(":"))
    except ValueError:
        print(f"Ungültige Uhrzeit: {args.at!r} (erwartet HH:MM)", file=sys.stderr)
        return 2
    console = Console()
    extra = " (mit E-Mail-Versand)" if args.email else ""
    console.print(
        f"[green]Scheduler gestartet[/green] – täglich um {args.at}{extra}. Strg+C zum Beenden."
    )
    run_daily(
        hour=hour,
        minute=minute,
        output_dir=args.output_dir,
        config_path=args.config,
        email=args.email,
        to=args.to,
    )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(directory=args.dir, host=args.host, port=args.port)
    return 0


def _cmd_web(args: argparse.Namespace) -> int:
    from .webapp import run_web

    run_web(
        host=args.host,
        port=args.port,
        output_dir=args.output_dir,
        config_path=args.config,
        token=args.token,
    )
    return 0


def _cmd_sources(args: argparse.Namespace) -> int:
    from rich.table import Table

    config = load_config()
    console = Console()
    table = Table(title="Konfigurierte Quellen")
    table.add_column("Quelle")
    table.add_column("Typ")
    table.add_column("Aktiv")
    table.add_column("Live")
    for s in config.sources:
        table.add_row(s.name, s.type.value, "✓" if s.enabled else "", "✓" if s.live else "")
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in (None, "run"):
        if args.command is None:
            args = parser.parse_args(["run", *(argv or [])])
        return _cmd_run(args)
    if args.command == "schedule":
        return _cmd_schedule(args)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "web":
        return _cmd_web(args)
    if args.command == "sources":
        return _cmd_sources(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
