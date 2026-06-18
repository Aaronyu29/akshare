"""Structured agent I/O schemas.

These dataclasses intentionally mirror the deterministic schemas without
requiring Pydantic. If the OpenAI Agents SDK requires Pydantic later, keep those
models in this file and convert at the adapter boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTriggerOutput:
    us_symbol: str
    trigger_summary: str
    trigger_type: str = "agent_verified"
    trigger_date: str = ""
    price_move: str = ""
    earnings_points: list[str] = field(default_factory=list)
    news_points: list[str] = field(default_factory=list)
    social_points: list[str] = field(default_factory=list)
    affected_supply_chain_links: list[str] = field(default_factory=list)
    confidence: str = "medium"
    sources: list[str] = field(default_factory=list)


@dataclass
class AgentEvidenceOutput:
    symbol: str
    evidence_tier: str = "unknown"
    customer_or_order_summary: str = ""
    estimated_exposure: str = ""
    source_quality: str = "unknown"
    risks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
