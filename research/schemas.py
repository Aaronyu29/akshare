"""Typed contracts for the deterministic research pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EvidenceTier(StrEnum):
    HARD = "hard"
    MEDIUM = "medium"
    SOFT = "soft"
    UNKNOWN = "unknown"


class CandidateClass(StrEnum):
    CORE = "core"
    WATCHLIST = "watchlist"
    AVOID_OVERHEATED = "avoid_overheated"
    AVOID_BLACK_HISTORY = "avoid_black_history"
    CONCEPT_ONLY = "concept_only"
    HARD_EXCLUDED = "hard_excluded"


class MarketType(StrEnum):
    A_SHARE = "a_share"
    ETF = "etf"


@dataclass
class Serializable:
    """Small dataclass serialization mixin."""

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def _serialize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


@dataclass
class DataWarning(Serializable):
    source: str
    message: str
    severity: str = "warning"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ResearchRequest(Serializable):
    us_symbol: str
    keywords: list[str] = field(default_factory=list)
    raw_context: str = ""
    holding_period: str = "several weeks to several months"
    risk_preference: str = "medium"
    market_scope: list[str] = field(default_factory=lambda: ["a_share", "etf"])
    exclusions: list[str] = field(
        default_factory=lambda: ["ST stocks", "Beijing Stock Exchange stocks"]
    )
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ThemeNode(Serializable):
    name: str
    keywords: list[str] = field(default_factory=list)
    children: list["ThemeNode"] = field(default_factory=list)


@dataclass
class TriggerPacket(Serializable):
    us_symbol: str
    trigger_date: str = field(default_factory=utc_now_iso)
    trigger_type: str = "user_context"
    trigger_summary: str = ""
    price_move: str = ""
    earnings_points: list[str] = field(default_factory=list)
    news_points: list[str] = field(default_factory=list)
    social_points: list[str] = field(default_factory=list)
    affected_supply_chain_links: list[str] = field(default_factory=list)
    confidence: str = "medium"
    sources: list[str] = field(default_factory=list)


@dataclass
class CandidateEvidence(Serializable):
    evidence_tier: EvidenceTier = EvidenceTier.UNKNOWN
    customer_or_order_summary: str = ""
    estimated_exposure: str = ""
    source_quality: str = "unknown"
    risks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CandidateMetrics(Serializable):
    latest_price: float | None = None
    pct_change: float | None = None
    turnover_amount: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    rsi: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    volume_expansion: float | None = None
    ma_distance: float | None = None
    fund_flow: float | None = None
    chip_profit_distribution: str = ""
    chip_loss_distribution: str = ""


@dataclass
class Candidate(Serializable):
    symbol: str
    name: str
    market_type: MarketType = MarketType.A_SHARE
    matched_theme: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    provider: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)
    evidence: CandidateEvidence = field(default_factory=CandidateEvidence)
    metrics: CandidateMetrics = field(default_factory=CandidateMetrics)
    risk_flags: list[str] = field(default_factory=list)
    data_warnings: list[DataWarning] = field(default_factory=list)
    candidate_class: CandidateClass = CandidateClass.WATCHLIST


@dataclass
class ScoreComponent(Serializable):
    name: str
    score: float
    max_score: float
    rationale: str = ""


@dataclass
class CandidateScore(Serializable):
    symbol: str
    total: float
    components: list[ScoreComponent] = field(default_factory=list)
    candidate_class: CandidateClass = CandidateClass.WATCHLIST


@dataclass
class EtfCandidate(Serializable):
    code: str
    name: str
    theme: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    tracking_index: str = ""
    management_fee: str = ""
    custody_fee: str = ""
    fund_size: float | None = None
    turnover: float | None = None
    premium_discount: float | None = None
    top_holdings: list[str] = field(default_factory=list)
    use_case: str = "fallback"
    provider: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)
    data_sources: list[str] = field(default_factory=list)
    data_warnings: list[DataWarning] = field(default_factory=list)


@dataclass
class TradingPlan(Serializable):
    symbol: str
    entry_conditions: list[str] = field(default_factory=list)
    take_profit_conditions: list[str] = field(default_factory=list)
    stop_loss_conditions: list[str] = field(default_factory=list)


@dataclass
class ResearchReport(Serializable):
    request: ResearchRequest
    trigger_packet: TriggerPacket
    theme_tree: list[ThemeNode] = field(default_factory=list)
    core_candidates: list[Candidate] = field(default_factory=list)
    watchlist: list[Candidate] = field(default_factory=list)
    avoid_overheated: list[Candidate] = field(default_factory=list)
    avoid_black_history: list[Candidate] = field(default_factory=list)
    concept_only: list[Candidate] = field(default_factory=list)
    etf_candidates: list[EtfCandidate] = field(default_factory=list)
    scores: dict[str, CandidateScore] = field(default_factory=dict)
    trading_plans: dict[str, TradingPlan] = field(default_factory=dict)
    data_warnings: list[DataWarning] = field(default_factory=list)
    follow_up_checks: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)
