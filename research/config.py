"""Configuration defaults for the research layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


RESEARCH_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ScoreWeights:
    theme_relevance: int = 30
    revenue_order_evidence: int = 25
    chip_structure: int = 15
    tradability: int = 15
    speculative_potential: int = 15
    min_risk_penalty: int = -30
    max_risk_penalty: int = 0


@dataclass(frozen=True)
class CacheSettings:
    cache_dir: Path = RESEARCH_ROOT / "cache"
    raw_dir: Path = RESEARCH_ROOT / "cache" / "raw"
    normalized_dir: Path = RESEARCH_ROOT / "cache" / "normalized"
    evidence_dir: Path = RESEARCH_ROOT / "cache" / "evidence"
    schema_version: str = "1"
    spot_ttl_seconds: int = 60 * 60 * 8
    history_ttl_seconds: int = 60 * 60 * 24
    etf_profile_ttl_seconds: int = 60 * 60 * 24 * 7
    board_ttl_seconds: int = 60 * 60 * 24
    financial_ttl_seconds: int = 60 * 60 * 24 * 7
    evidence_ttl_seconds: int = 60 * 60 * 24 * 30


@dataclass(frozen=True)
class ResearchSettings:
    market_scope: tuple[str, ...] = ("a_share", "etf")
    hard_excluded_boards: tuple[str, ...] = ("bse",)
    hard_excluded_name_tokens: tuple[str, ...] = ("ST", "*ST")
    core_candidate_target: int = 3
    max_core_candidates: int = 8
    default_rsi_overheated: float = 75.0
    warning_rsi: float = 70.0
    recent_return_overheated: float = 0.35
    min_turnover_amount: float = 30_000_000.0
    report_dir: Path = RESEARCH_ROOT / "reports"
    score_weights: ScoreWeights = field(default_factory=ScoreWeights)
    cache: CacheSettings = field(default_factory=CacheSettings)


def get_default_settings() -> ResearchSettings:
    """Return immutable default research settings."""
    return ResearchSettings()
