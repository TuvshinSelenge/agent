"""Daily scheduling of the orchestrator (default: every morning at 06:00)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .orchestrator import Orchestrator
from .report import render_console
from .runner import write_outputs


def run_daily(
    hour: int = 6,
    minute: int = 0,
    output_dir: str | Path = "output",
    config_path: str | Path | None = None,
    on_run: Callable[[], None] | None = None,
) -> None:
    """Block and run the orchestrator every day at the given local time."""
    scheduler = BlockingScheduler()

    @scheduler.scheduled_job(CronTrigger(hour=hour, minute=minute))
    def _job() -> None:  # pragma: no cover - exercised via manual/integration runs
        orchestrator = Orchestrator()
        report = orchestrator.run()
        render_console(report)
        write_outputs(report, output_dir)
        if on_run:
            on_run()

    scheduler.start()
