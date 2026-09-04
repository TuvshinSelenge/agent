"""ELK Lead Agent.

An orchestrator plus specialized agents that scan Austrian public sources daily
for new temporary-/employee-housing and hospitality projects, score them against
a configurable rubric, and emit a morning report of sales leads.
"""

from .config import Config, load_config
from .orchestrator import Orchestrator

__version__ = "0.1.0"
__all__ = ["Orchestrator", "Config", "load_config", "__version__"]
