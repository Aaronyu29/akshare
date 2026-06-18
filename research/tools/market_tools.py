"""Market data tool wrappers for optional agent integration."""

from __future__ import annotations

from ..data_sources import fetch_a_stock_spot, fetch_etf_spot
from ..schemas import ResearchRequest, TriggerPacket
from ..universe import build_candidate_universe


def tool_fetch_a_stock_spot() -> dict[str, object]:
    result = fetch_a_stock_spot()
    return {
        "provider": result.provider,
        "row_count": result.row_count,
        "warnings": list(result.warnings),
    }


def tool_fetch_etf_spot() -> dict[str, object]:
    result = fetch_etf_spot()
    return {
        "provider": result.provider,
        "row_count": result.row_count,
        "warnings": list(result.warnings),
    }


def tool_build_candidate_universe(
    us_symbol: str,
    keywords: list[str],
    raw_context: str = "",
) -> dict[str, object]:
    request = ResearchRequest(
        us_symbol=us_symbol,
        keywords=keywords,
        raw_context=raw_context,
    )
    trigger = TriggerPacket(us_symbol=us_symbol, trigger_summary=raw_context)
    stocks, etfs, themes, warnings = build_candidate_universe(request, trigger)
    return {
        "stocks": [stock.to_dict() for stock in stocks],
        "etfs": [etf.to_dict() for etf in etfs],
        "themes": [theme.to_dict() for theme in themes],
        "warnings": [warning.to_dict() for warning in warnings],
    }
