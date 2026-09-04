"""Base class and shared plumbing for collector agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Config, SourceConfig
from ..models import RawFinding
from .fixtures import FixtureProvider


class SourceAgent(ABC):
    """A collector agent responsible for one public source.

    Each agent knows how to turn its source into a list of :class:`RawFinding`.
    Live network access is optional and best-effort: when it fails, agents fall
    back to bundled fixtures so the whole pipeline still runs deterministically.
    """

    def __init__(self, source: SourceConfig, config: Config, fixtures: FixtureProvider):
        self.source = source
        self.config = config
        self.fixtures = fixtures

    @property
    def name(self) -> str:
        return self.source.name

    def collect(self) -> list[RawFinding]:
        if self.source.live:
            try:
                findings = self.fetch_live()
                if findings:
                    return findings
            except Exception:  # noqa: BLE001 - degrade gracefully to fixtures
                pass
        return self.fetch_fixtures()

    def fetch_fixtures(self) -> list[RawFinding]:
        return self.fixtures.for_source(self.source.name)

    @abstractmethod
    def fetch_live(self) -> list[RawFinding]:
        """Attempt a real network fetch. Raise or return [] to fall back."""
        raise NotImplementedError
