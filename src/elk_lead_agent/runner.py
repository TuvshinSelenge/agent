"""Shared helpers for running the orchestrator and writing report artifacts."""

from __future__ import annotations

from pathlib import Path

from . import report as report_mod
from .models import RunReport


def write_outputs(report: RunReport, output_dir: str | Path = "output") -> dict[str, Path]:
    """Write Markdown, HTML and JSON renderings of the report to ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%d_%H%M%S")

    paths = {
        "markdown": out / f"report_{stamp}.md",
        "html": out / f"report_{stamp}.html",
        "json": out / f"report_{stamp}.json",
        "latest_markdown": out / "report_latest.md",
        "latest_html": out / "report_latest.html",
    }
    md = report_mod.to_markdown(report)
    html = report_mod.to_html(report)
    js = report_mod.to_json(report)

    paths["markdown"].write_text(md, encoding="utf-8")
    paths["html"].write_text(html, encoding="utf-8")
    paths["json"].write_text(js, encoding="utf-8")
    paths["latest_markdown"].write_text(md, encoding="utf-8")
    paths["latest_html"].write_text(html, encoding="utf-8")
    return paths
