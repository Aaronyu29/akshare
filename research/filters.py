"""Hard exclusions and soft risk flags for candidates."""

from __future__ import annotations

from .config import ResearchSettings, get_default_settings
from .schemas import Candidate, CandidateClass


def apply_filters(
    candidates: list[Candidate],
    settings: ResearchSettings | None = None,
) -> tuple[list[Candidate], list[Candidate]]:
    """Apply hard and soft filters.

    Returns active candidates and hard-excluded candidates.
    """
    settings = settings or get_default_settings()
    active: list[Candidate] = []
    excluded: list[Candidate] = []
    for candidate in candidates:
        if _is_bse(candidate.symbol):
            candidate.risk_flags.append("hard_exclusion_bse")
            candidate.candidate_class = CandidateClass.HARD_EXCLUDED
            excluded.append(candidate)
            continue
        if _is_st(candidate.name, settings):
            candidate.risk_flags.append("hard_exclusion_st")
            candidate.candidate_class = CandidateClass.HARD_EXCLUDED
            excluded.append(candidate)
            continue
        if "black_history_confirmed" in candidate.risk_flags:
            candidate.candidate_class = CandidateClass.AVOID_BLACK_HISTORY
            excluded.append(candidate)
            continue
        _apply_soft_flags(candidate, settings)
        active.append(candidate)
    return active, excluded


def _apply_soft_flags(candidate: Candidate, settings: ResearchSettings) -> None:
    metrics = candidate.metrics
    if metrics.rsi is not None and metrics.rsi >= settings.default_rsi_overheated:
        candidate.risk_flags.append("overheated_rsi")
        candidate.candidate_class = CandidateClass.AVOID_OVERHEATED
    elif metrics.rsi is not None and metrics.rsi >= settings.warning_rsi:
        candidate.risk_flags.append("warning_rsi_high")

    if (
        metrics.return_20d is not None
        and metrics.return_20d >= settings.recent_return_overheated
    ):
        candidate.risk_flags.append("overheated_recent_return")
        candidate.candidate_class = CandidateClass.AVOID_OVERHEATED

    if (
        metrics.turnover_amount is not None
        and metrics.turnover_amount < settings.min_turnover_amount
    ):
        candidate.risk_flags.append("weak_liquidity")

    if candidate.evidence.evidence_tier.value in {"soft", "unknown"}:
        candidate.risk_flags.append("weak_evidence")


def _is_bse(symbol: str) -> bool:
    clean = symbol.lower().replace("bj", "")
    return symbol.lower().startswith("bj") or clean.startswith(("4", "8", "9"))


def _is_st(name: str, settings: ResearchSettings) -> bool:
    upper_name = name.upper()
    return any(token in upper_name for token in settings.hard_excluded_name_tokens)
