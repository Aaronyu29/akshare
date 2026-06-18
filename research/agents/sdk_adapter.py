"""Optional OpenAI Agents SDK adapter.

The deterministic research pipeline must work without this dependency. This file
provides an import-safe adapter boundary for later SDK usage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .prompts import (
    EVIDENCE_AGENT_INSTRUCTIONS,
    REPORT_AGENT_INSTRUCTIONS,
    RISK_AGENT_INSTRUCTIONS,
    TRIGGER_RESEARCH_INSTRUCTIONS,
)


@dataclass(frozen=True)
class AgentsSdkStatus:
    available: bool
    message: str


def get_agents_sdk_status() -> AgentsSdkStatus:
    try:
        import agents  # noqa: F401
    except ImportError:
        return AgentsSdkStatus(
            available=False,
            message="openai-agents SDK is not installed; manual mode is active",
        )
    return AgentsSdkStatus(available=True, message="openai-agents SDK is available")


def build_agent_definitions() -> dict[str, dict[str, Any]]:
    """Return declarative agent definitions without requiring SDK imports."""
    return {
        "TriggerResearchAgent": {
            "instructions": TRIGGER_RESEARCH_INSTRUCTIONS,
            "tools": ["fetch_a_stock_spot", "fetch_etf_spot"],
        },
        "EvidenceAgent": {
            "instructions": EVIDENCE_AGENT_INSTRUCTIONS,
            "tools": ["build_candidate_universe", "score_candidates"],
        },
        "RiskAgent": {
            "instructions": RISK_AGENT_INSTRUCTIONS,
            "tools": ["score_candidates"],
        },
        "ReportAgent": {
            "instructions": REPORT_AGENT_INSTRUCTIONS,
            "tools": ["write_markdown_report"],
        },
    }


def require_agents_sdk() -> None:
    status = get_agents_sdk_status()
    if not status.available:
        raise RuntimeError(status.message)
