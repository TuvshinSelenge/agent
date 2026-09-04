"""The orchestrator: coordinates collector agents and the analysis pipeline.

Flow (one daily run):

    collectors (concurrent)  ->  analyst (categorize + score)
        ->  relevance filter  ->  dedupe  ->  24h window  ->  unseen filter
        ->  enrichment  ->  RunReport (sorted, leads flagged)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

from . import dedup, enrichment, scoring
from .config import Config, load_config
from .models import RawFinding, RunReport, ScoredProject
from .sources import FixtureProvider, build_agents
from .state import StateStore


class Orchestrator:
    def __init__(
        self,
        config: Config | None = None,
        fixtures: FixtureProvider | None = None,
        state: StateStore | None = None,
        now: datetime | None = None,
        max_workers: int = 8,
        live_only: bool = False,
    ):
        self.config = config or load_config()
        self.now = now or datetime.now(UTC)
        self.fixtures = fixtures or FixtureProvider(now=self.now)
        self.state = state if state is not None else StateStore()
        self.max_workers = max_workers
        # When True, only real network sources are used (no fixtures), so every
        # reported "Link zur Quelle" points at a genuine, resolvable URL.
        self.live_only = live_only

    def _collect_all(self) -> tuple[list[RawFinding], list[str], list[str]]:
        agents = build_agents(self.config, self.fixtures)
        findings: list[RawFinding] = []
        queried: list[str] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(a.collect, self.live_only): a for a in agents}
            for future in as_completed(futures):
                agent = futures[future]
                queried.append(agent.name)
                try:
                    findings.extend(future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{agent.name}: {exc}")
        return findings, sorted(queried), errors

    def _within_window(self, finding: RawFinding) -> bool:
        cutoff = self.now - timedelta(hours=self.config.window_hours)
        return finding.published_at >= cutoff

    def run(self, persist_state: bool = True) -> RunReport:
        findings, queried, errors = self._collect_all()

        # Analyst agent: categorize + score, keep only relevant findings.
        scored: list[ScoredProject] = []
        for finding in findings:
            project = scoring.analyze(finding, self.config)
            if scoring.is_relevant(project):
                scored.append(project)

        # Apply the 24h window BEFORE dedup: otherwise an out-of-window duplicate
        # with a higher score could be kept and then dropped by the window filter,
        # discarding a valid in-window update that shares its fingerprint.
        scored = [p for p in scored if self._within_window(p.finding)]
        scored = dedup.dedupe(scored)
        scored = [p for p in scored if not self.state.is_seen(p.fingerprint)]

        for project in scored:
            enrichment.enrich(project, self.config)

        scored.sort(key=lambda p: (p.score, p.finding.published_at), reverse=True)

        report = RunReport(
            generated_at=self.now,
            window_hours=self.config.window_hours,
            threshold_lead=self.config.threshold_lead,
            projects=scored,
            sources_queried=queried,
            errors=errors,
        )

        if persist_state:
            self.commit_seen(report)

        return report

    def commit_seen(self, report: RunReport) -> None:
        """Mark the report's projects as seen and persist state.

        Call this only AFTER the report has been delivered successfully (written
        and/or e-mailed), so a delivery failure does not silently drop leads from
        every future run.
        """
        self.state.mark_seen([p.fingerprint for p in report.projects])
        self.state.save()
