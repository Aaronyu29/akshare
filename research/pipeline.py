"""Deterministic research pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from .config import ResearchSettings, get_default_settings
from .enrichment import enrich_candidates
from .filters import apply_filters
from .mappings import get_theme_tree
from .report import write_markdown_report
from .schemas import (
    Candidate,
    CandidateClass,
    DataWarning,
    ResearchReport,
    ResearchRequest,
    TradingPlan,
    TriggerPacket,
)
from .scoring import score_candidates
from .universe import build_candidate_universe


def build_trigger_packet(request: ResearchRequest) -> TriggerPacket:
    """Build a minimal trigger packet from user-provided context."""
    points = [line.strip() for line in request.raw_context.splitlines() if line.strip()]
    return TriggerPacket(
        us_symbol=request.us_symbol.upper(),
        trigger_summary=request.raw_context.strip()
        or f"User requested research for {request.us_symbol.upper()}",
        news_points=points,
        affected_supply_chain_links=request.keywords,
        confidence="manual",
    )


def run_research(
    request: ResearchRequest,
    settings: ResearchSettings | None = None,
    use_live_data: bool = True,
    output_dir: Path | None = None,
) -> tuple[ResearchReport, Path]:
    """Run the deterministic pipeline and write a Markdown report."""
    settings = settings or get_default_settings()
    trigger = build_trigger_packet(request)
    candidates, etfs, theme_tree, warnings = build_candidate_universe(
        request,
        trigger,
        use_live_data=use_live_data,
    )
    candidates, etfs, enrichment_warnings = enrich_candidates(
        candidates,
        etfs,
        use_live_data=use_live_data,
    )
    warnings.extend(enrichment_warnings)
    active_candidates, excluded_candidates = apply_filters(candidates, settings)
    scores = score_candidates(active_candidates, settings)

    all_candidates = active_candidates + excluded_candidates
    report = ResearchReport(
        request=request,
        trigger_packet=trigger,
        theme_tree=theme_tree or get_theme_tree(request.us_symbol, request.keywords),
        core_candidates=_by_class(all_candidates, CandidateClass.CORE),
        watchlist=_by_class(all_candidates, CandidateClass.WATCHLIST),
        avoid_overheated=_by_class(all_candidates, CandidateClass.AVOID_OVERHEATED),
        avoid_black_history=_by_class(all_candidates, CandidateClass.AVOID_BLACK_HISTORY),
        concept_only=_by_class(all_candidates, CandidateClass.CONCEPT_ONLY),
        etf_candidates=etfs,
        scores=scores,
        trading_plans=_build_trading_plans(all_candidates),
        data_warnings=warnings,
        follow_up_checks=_default_follow_up_checks(request, all_candidates, etfs),
    )
    if excluded_candidates:
        report.data_warnings.extend(
            DataWarning(
                source="filters",
                message=f"{item.symbol} {item.name} was hard excluded: {', '.join(item.risk_flags)}",
            )
            for item in excluded_candidates
        )
    path = write_markdown_report(report, output_dir=output_dir or settings.report_dir)
    return report, path


def _by_class(candidates: list[Candidate], candidate_class: CandidateClass) -> list[Candidate]:
    return [candidate for candidate in candidates if candidate.candidate_class == candidate_class]


def _build_trading_plans(candidates: list[Candidate]) -> dict[str, TradingPlan]:
    plans: dict[str, TradingPlan] = {}
    for candidate in candidates:
        entry = [
            "Wait for RSI/short-term heat to cool if overheated.",
            "Prefer entry after theme pullback and support confirmation.",
            "Require evidence to remain intact before action.",
        ]
        take_profit = [
            "Take profit when theme becomes crowded or valuation rerates sharply.",
            "Reduce exposure after catalyst is fully priced in.",
        ]
        stop_loss = [
            "Invalidate if order/customer evidence is disproved.",
            "Stop out if price breaks key support with sector heat collapsing.",
            "Exit if serious disclosure/governance red flags appear.",
        ]
        if "overheated_rsi" in candidate.risk_flags:
            entry.insert(0, "Do not chase while RSI is overheated.")
        if candidate.evidence.evidence_tier.value in {"soft", "unknown"}:
            entry.append("Upgrade evidence tier before treating as core position.")
        plans[candidate.symbol] = TradingPlan(
            symbol=candidate.symbol,
            entry_conditions=entry,
            take_profit_conditions=take_profit,
            stop_loss_conditions=stop_loss,
        )
    return plans


def _default_follow_up_checks(
    request: ResearchRequest,
    candidates: list[Candidate],
    etfs: list,
) -> list[str]:
    checks = [
        f"Verify latest US-side trigger for {request.us_symbol.upper()} with external sources.",
        "Check whether customer/order exposure reaches or approaches 30%.",
        "Review announcements, annual reports, investor Q&A, and research notes for hard evidence.",
        "Check RSI, recent return, turnover, and board heat before entry.",
        "Check black-history and governance red flags before promotion to core.",
    ]
    if not candidates:
        checks.append("Candidate universe is empty; broaden keywords or verify data sources.")
    if not etfs:
        checks.append("ETF list is empty; verify ETF data source and theme keywords.")
    return checks
