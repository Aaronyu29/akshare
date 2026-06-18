"""Markdown report rendering."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .mappings import theme_slug
from .schemas import (
    Candidate,
    EtfCandidate,
    ResearchReport,
    ScoreComponent,
    ThemeNode,
    TradingPlan,
)


def report_filename(report: ResearchReport) -> str:
    symbol = report.request.us_symbol.upper()
    theme = theme_slug("-".join(report.request.keywords[:3]) or symbol)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{symbol}_{theme}_{stamp}.md"


def write_markdown_report(report: ResearchReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / report_filename(report)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path


def render_markdown_report(report: ResearchReport) -> str:
    lines: list[str] = []
    lines.append(f"# {report.request.us_symbol.upper()} A-share Research Pack")
    lines.append("")
    lines.append("## Run Metadata")
    lines.append("")
    lines.append(f"- Generated at: `{report.generated_at}`")
    lines.append(f"- Holding period: {report.request.holding_period}")
    lines.append(f"- Market scope: {', '.join(report.request.market_scope)}")
    lines.append(f"- Exclusions: {', '.join(report.request.exclusions)}")
    lines.append("")
    lines.append("## User Input")
    lines.append("")
    lines.append(f"- US symbol: `{report.request.us_symbol.upper()}`")
    lines.append(f"- Keywords: {', '.join(report.request.keywords) or 'none'}")
    if report.request.raw_context:
        lines.append("")
        lines.append("```text")
        lines.append(report.request.raw_context.strip())
        lines.append("```")
    lines.append("")
    lines.append("## US Trigger Summary")
    lines.append("")
    lines.append(report.trigger_packet.trigger_summary or "No trigger summary provided.")
    lines.append("")
    if report.trigger_packet.news_points:
        lines.append("- News/user points:")
        lines.extend(f"  - {item}" for item in report.trigger_packet.news_points)
        lines.append("")
    lines.append("## Theme Tree")
    lines.append("")
    if report.theme_tree:
        for node in report.theme_tree:
            _render_theme_node(lines, node, depth=0)
    else:
        lines.append("- No theme tree available.")
    lines.append("")
    lines.append("## Core Stock Candidates")
    lines.append("")
    _render_candidate_table(lines, report, report.core_candidates)
    lines.append("")
    lines.append("## Watchlist")
    lines.append("")
    _render_candidate_table(lines, report, report.watchlist)
    lines.append("")
    lines.append("## Avoid / Overheated")
    lines.append("")
    _render_candidate_table(lines, report, report.avoid_overheated)
    lines.append("")
    lines.append("## Avoid / Black History")
    lines.append("")
    _render_candidate_table(lines, report, report.avoid_black_history)
    lines.append("")
    lines.append("## ETF Implementation")
    lines.append("")
    _render_etf_table(lines, report.etf_candidates)
    lines.append("")
    lines.append("## Trading Plans")
    lines.append("")
    _render_trading_plans(lines, report.trading_plans)
    lines.append("")
    lines.append("## Data Warnings")
    lines.append("")
    if report.data_warnings:
        for warning in report.data_warnings:
            lines.append(f"- `{warning.source}`: {warning.message}")
    else:
        lines.append("- None.")
    lines.append("")
    lines.append("## Follow-Up Checks")
    lines.append("")
    for check in report.follow_up_checks:
        lines.append(f"- {check}")
    lines.append("")
    lines.append("## Disclaimer")
    lines.append("")
    lines.append("This report is for research screening only and is not financial advice.")
    lines.append("")
    return "\n".join(lines)


def _render_theme_node(lines: list[str], node: ThemeNode, depth: int) -> None:
    indent = "  " * depth
    keywords = f" ({', '.join(node.keywords[:5])})" if node.keywords else ""
    lines.append(f"{indent}- {node.name}{keywords}")
    for child in node.children:
        _render_theme_node(lines, child, depth + 1)


def _render_candidate_table(
    lines: list[str],
    report: ResearchReport,
    candidates: list[Candidate],
) -> None:
    if not candidates:
        lines.append("No candidates in this section.")
        return
    lines.append(
        "| Symbol | Name | Match | Score | Evidence | Risk Flags | Entry Summary |"
    )
    lines.append("| --- | --- | --- | ---: | --- | --- | --- |")
    for candidate in candidates:
        score = report.scores.get(candidate.symbol)
        plan = report.trading_plans.get(candidate.symbol)
        entry = "; ".join(plan.entry_conditions[:2]) if plan else ""
        lines.append(
            "| {symbol} | {name} | {match} | {score} | {evidence} | {risks} | {entry} |".format(
                symbol=candidate.symbol,
                name=candidate.name,
                match=candidate.matched_theme or ", ".join(candidate.matched_keywords[:2]),
                score=f"{score.total:.1f}" if score else "n/a",
                evidence=_evidence_summary(candidate),
                risks=", ".join(candidate.risk_flags) or "none",
                entry=entry,
            )
        )
        if score:
            component_text = "; ".join(_component_summary(item) for item in score.components)
            lines.append(
                f"|  |  | score detail |  | {component_text} |  |  |"
            )


def _render_etf_table(lines: list[str], etfs: list[EtfCandidate]) -> None:
    if not etfs:
        lines.append("No ETF candidates matched. Verify ETF data source and keywords.")
        return
    lines.append(
        "| Code | Name | Theme | Fee Notes | Size/Liquidity | Tracking | Use Case |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for etf in etfs:
        fee = f"mgmt: {etf.management_fee or 'pending'}; custody: {etf.custody_fee or 'pending'}"
        size_liquidity = f"size: {_fmt(etf.fund_size)}; turnover: {_fmt(etf.turnover)}"
        lines.append(
            f"| {etf.code} | {etf.name} | {etf.theme} | {fee} | {size_liquidity} | {etf.tracking_index or 'pending'} | {etf.use_case} |"
        )


def _render_trading_plans(lines: list[str], plans: dict[str, TradingPlan]) -> None:
    if not plans:
        lines.append("No trading plans generated.")
        return
    lines.append("| Symbol | Entry Conditions | Take Profit | Stop Loss / Invalidation |")
    lines.append("| --- | --- | --- | --- |")
    for symbol, plan in plans.items():
        lines.append(
            "| {symbol} | {entry} | {take_profit} | {stop_loss} |".format(
                symbol=symbol,
                entry="<br>".join(plan.entry_conditions),
                take_profit="<br>".join(plan.take_profit_conditions),
                stop_loss="<br>".join(plan.stop_loss_conditions),
            )
        )


def _evidence_summary(candidate: Candidate) -> str:
    if candidate.evidence.customer_or_order_summary:
        return f"{candidate.evidence.evidence_tier.value}: {candidate.evidence.customer_or_order_summary}"
    return candidate.evidence.evidence_tier.value


def _component_summary(component: ScoreComponent) -> str:
    return f"{component.name}={component.score:g}/{component.max_score:g} ({component.rationale})"


def _fmt(value: float | None) -> str:
    if value is None:
        return "pending"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f}e"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f}w"
    return f"{value:.2f}"
