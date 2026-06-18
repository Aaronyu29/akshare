"""Candidate scoring rules."""

from __future__ import annotations

from .config import ResearchSettings, get_default_settings
from .schemas import (
    Candidate,
    CandidateClass,
    CandidateScore,
    EvidenceTier,
    ScoreComponent,
)


def score_candidates(
    candidates: list[Candidate],
    settings: ResearchSettings | None = None,
) -> dict[str, CandidateScore]:
    settings = settings or get_default_settings()
    scores = {candidate.symbol: score_candidate(candidate, settings) for candidate in candidates}
    _classify(candidates, scores, settings)
    return scores


def score_candidate(
    candidate: Candidate,
    settings: ResearchSettings | None = None,
) -> CandidateScore:
    settings = settings or get_default_settings()
    weights = settings.score_weights
    components = [
        _theme_score(candidate, weights.theme_relevance),
        _evidence_score(candidate, weights.revenue_order_evidence),
        _chip_score(candidate, weights.chip_structure),
        _tradability_score(candidate, weights.tradability),
        _speculation_score(candidate, weights.speculative_potential),
        _risk_score(candidate, weights.min_risk_penalty),
    ]
    total = sum(component.score for component in components)
    return CandidateScore(
        symbol=candidate.symbol,
        total=round(total, 2),
        components=components,
        candidate_class=candidate.candidate_class,
    )


def _theme_score(candidate: Candidate, max_score: int) -> ScoreComponent:
    matched = len(candidate.matched_keywords)
    provenance_bonus = min(len(candidate.provenance) * 2, 8)
    score = min(max_score, 8 + matched * 3 + provenance_bonus)
    return ScoreComponent(
        name="theme_relevance",
        score=float(score),
        max_score=float(max_score),
        rationale=f"{matched} matched keywords; {len(candidate.provenance)} provenance items",
    )


def _evidence_score(candidate: Candidate, max_score: int) -> ScoreComponent:
    tier = candidate.evidence.evidence_tier
    base = {
        EvidenceTier.HARD: 18,
        EvidenceTier.MEDIUM: 12,
        EvidenceTier.SOFT: 6,
        EvidenceTier.UNKNOWN: 3,
    }.get(tier, 3)
    summary = candidate.evidence.customer_or_order_summary.lower()
    exposure = candidate.evidence.estimated_exposure.lower()
    bonus = 0
    if "30" in exposure or "30%" in summary:
        bonus += 5
    if any(token in summary for token in ["large order", "major order", "大订单"]):
        bonus += 5
    score = min(max_score, base + bonus)
    return ScoreComponent(
        name="revenue_order_evidence",
        score=float(score),
        max_score=float(max_score),
        rationale=f"evidence tier {tier.value}; exposure {candidate.evidence.estimated_exposure or 'unknown'}",
    )


def _chip_score(candidate: Candidate, max_score: int) -> ScoreComponent:
    metrics = candidate.metrics
    score = 5
    notes: list[str] = []
    if metrics.chip_profit_distribution:
        score += 4
        notes.append("profit distribution available")
    if metrics.chip_loss_distribution:
        score += 3
        notes.append("loss distribution available")
    if metrics.volume_expansion is not None and metrics.volume_expansion > 1.2:
        score += 2
        notes.append("volume expansion")
    return ScoreComponent(
        name="chip_structure",
        score=float(min(max_score, score)),
        max_score=float(max_score),
        rationale=", ".join(notes) or "chip data limited",
    )


def _tradability_score(candidate: Candidate, max_score: int) -> ScoreComponent:
    metrics = candidate.metrics
    score = 5
    notes: list[str] = []
    if metrics.turnover_amount is not None:
        if metrics.turnover_amount >= 300_000_000:
            score += 7
            notes.append("strong turnover")
        elif metrics.turnover_amount >= 50_000_000:
            score += 5
            notes.append("acceptable turnover")
        else:
            score -= 2
            notes.append("weak turnover")
    if metrics.rsi is not None and metrics.rsi < 70:
        score += 3
        notes.append("RSI not overheated")
    return ScoreComponent(
        name="tradability",
        score=float(max(0, min(max_score, score))),
        max_score=float(max_score),
        rationale=", ".join(notes) or "limited tradability data",
    )


def _speculation_score(candidate: Candidate, max_score: int) -> ScoreComponent:
    score = 5 + min(len(candidate.matched_keywords), 5)
    if any("board" in item.lower() for item in candidate.provenance):
        score += 3
    if "overheated_rsi" in candidate.risk_flags:
        score -= 4
    return ScoreComponent(
        name="speculative_potential",
        score=float(max(0, min(max_score, score))),
        max_score=float(max_score),
        rationale="theme narrative and board provenance",
    )


def _risk_score(candidate: Candidate, min_score: int) -> ScoreComponent:
    penalty = 0
    rationale: list[str] = []
    penalty_map = {
        "overheated_rsi": -8,
        "overheated_recent_return": -8,
        "weak_liquidity": -5,
        "weak_evidence": -4,
        "black_history_suspected": -10,
    }
    for flag in candidate.risk_flags:
        value = penalty_map.get(flag, 0)
        if value:
            penalty += value
            rationale.append(flag)
    return ScoreComponent(
        name="risk_penalty",
        score=float(max(min_score, penalty)),
        max_score=0.0,
        rationale=", ".join(rationale) or "no major risk flags",
    )


def _classify(
    candidates: list[Candidate],
    scores: dict[str, CandidateScore],
    settings: ResearchSettings,
) -> None:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.candidate_class not in {CandidateClass.AVOID_OVERHEATED, CandidateClass.AVOID_BLACK_HISTORY}
        and "weak_liquidity" not in candidate.risk_flags
    ]
    eligible.sort(key=lambda item: scores[item.symbol].total, reverse=True)
    core_symbols = {candidate.symbol for candidate in eligible[: settings.core_candidate_target]}
    for candidate in candidates:
        if candidate.symbol in core_symbols:
            candidate.candidate_class = CandidateClass.CORE
        elif candidate.candidate_class == CandidateClass.WATCHLIST:
            candidate.candidate_class = CandidateClass.WATCHLIST
        scores[candidate.symbol].candidate_class = candidate.candidate_class
