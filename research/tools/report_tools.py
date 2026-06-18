"""Report tool wrappers for optional agent integration."""

from __future__ import annotations

from pathlib import Path

from ..report import render_markdown_report, write_markdown_report
from ..schemas import ResearchReport


def tool_render_markdown_report(report: ResearchReport) -> str:
    return render_markdown_report(report)


def tool_write_markdown_report(report: ResearchReport, output_dir: str | Path) -> str:
    return str(write_markdown_report(report, Path(output_dir)))
