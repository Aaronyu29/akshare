"""Candidate universe construction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import akshare as ak
import pandas as pd

from . import data_sources
from .mappings import expand_keywords, get_theme_tree
from .schemas import (
    Candidate,
    DataWarning,
    EtfCandidate,
    MarketType,
    ResearchRequest,
    ThemeNode,
    TriggerPacket,
)


def build_candidate_universe(
    request: ResearchRequest,
    trigger: TriggerPacket | None = None,
    use_live_data: bool = True,
) -> tuple[list[Candidate], list[EtfCandidate], list[ThemeNode], list[DataWarning]]:
    """Build stock and ETF candidates with best-effort provider fallbacks."""
    trigger = trigger or TriggerPacket(us_symbol=request.us_symbol)
    keywords = expand_keywords(request.us_symbol, request.keywords)
    theme_tree = get_theme_tree(request.us_symbol, keywords)
    warnings: list[DataWarning] = []
    stock_candidates: dict[str, Candidate] = {}
    etf_candidates: dict[str, EtfCandidate] = {}

    if not use_live_data:
        warnings.append(
            DataWarning(
                source="universe",
                message="live data disabled; generated theme tree without market universe",
            )
        )
        return [], [], theme_tree, warnings

    try:
        stock_result = data_sources.fetch_a_stock_spot()
        warnings.extend(data_sources.warnings_to_data_warnings(stock_result, "a_stock_spot"))
        _add_stock_name_matches(stock_candidates, stock_result.data, keywords, stock_result.provider)
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            DataWarning(
                source="a_stock_spot",
                message=f"failed to fetch A-share spot data: {type(exc).__name__}: {exc}",
            )
        )

    try:
        etf_result = data_sources.fetch_etf_spot()
        warnings.extend(data_sources.warnings_to_data_warnings(etf_result, "etf_spot"))
        _add_etf_name_matches(etf_candidates, etf_result.data, keywords, etf_result.provider)
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            DataWarning(
                source="etf_spot",
                message=f"failed to fetch ETF spot data: {type(exc).__name__}: {exc}",
            )
        )

    _add_board_matches(stock_candidates, keywords, warnings)

    if not stock_candidates:
        warnings.append(
            DataWarning(
                source="universe",
                message="no stock candidates matched; report will contain ETF/data warnings only",
            )
        )
    if not etf_candidates:
        warnings.append(
            DataWarning(
                source="universe",
                message="no ETF candidates matched; check keyword mapping or data-source availability",
            )
        )

    return (
        list(stock_candidates.values()),
        list(etf_candidates.values()),
        theme_tree,
        warnings,
    )


def _add_stock_name_matches(
    candidates: dict[str, Candidate],
    frame: pd.DataFrame,
    keywords: list[str],
    provider: str,
) -> None:
    code_col = _first_col(frame, ["代码", "code", "证券代码", "f12"])
    name_col = _first_col(frame, ["名称", "name", "证券简称", "f14"])
    if code_col is None or name_col is None:
        return
    fetched_at = _now_iso()
    for _, row in frame.iterrows():
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        matched = _matched_keywords(f"{code} {name}", keywords)
        if not code or not name or not matched:
            continue
        candidate = candidates.get(code)
        provenance = [f"name match via {provider}: {', '.join(matched[:5])}"]
        if candidate is None:
            candidates[code] = Candidate(
                symbol=code,
                name=name,
                market_type=MarketType.A_SHARE,
                matched_theme=matched[0],
                matched_keywords=matched,
                provenance=provenance,
                provider=provider,
                fetched_at=fetched_at,
            )
        else:
            _merge_candidate(candidate, matched, provenance)


def _add_etf_name_matches(
    candidates: dict[str, EtfCandidate],
    frame: pd.DataFrame,
    keywords: list[str],
    provider: str,
) -> None:
    code_col = _first_col(frame, ["代码", "基金代码", "code", "f12"])
    name_col = _first_col(frame, ["名称", "基金名称", "name", "f14"])
    if code_col is None or name_col is None:
        return
    fetched_at = _now_iso()
    for _, row in frame.iterrows():
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        matched = _matched_keywords(f"{code} {name}", keywords)
        if not code or not name or not matched:
            continue
        turnover = _to_float(row.get(_first_col(frame, ["成交额", "amount", "f6"])))
        size = _to_float(row.get(_first_col(frame, ["总市值", "最新份额", "fund_size"])))
        candidates[code] = EtfCandidate(
            code=code,
            name=name,
            theme=matched[0],
            matched_keywords=matched,
            turnover=turnover,
            fund_size=size,
            provider=provider,
            fetched_at=fetched_at,
            data_sources=[f"ETF name match via {provider}"],
        )


def _add_board_matches(
    candidates: dict[str, Candidate],
    keywords: list[str],
    warnings: list[DataWarning],
) -> None:
    board_sources = [
        ("concept", data_sources.fetch_concept_board_names, ak.stock_board_concept_cons_em),
        ("industry", data_sources.fetch_industry_board_names, ak.stock_board_industry_cons_em),
    ]
    for board_type, fetch_names, fetch_cons in board_sources:
        try:
            boards = fetch_names()
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                DataWarning(
                    source=f"{board_type}_boards",
                    message=f"failed to fetch {board_type} board names: {type(exc).__name__}: {exc}",
                )
            )
            continue
        warnings.extend(data_sources.warnings_to_data_warnings(boards, f"{board_type}_boards"))
        board_name_col = _first_col(boards.data, ["板块名称", "名称", "name", "概念名称"])
        if board_name_col is None:
            continue
        matched_boards: list[str] = []
        for _, row in boards.data.iterrows():
            board_name = str(row.get(board_name_col, "")).strip()
            if board_name and _matched_keywords(board_name, keywords):
                matched_boards.append(board_name)
        for board_name in matched_boards[:8]:
            try:
                cons = fetch_cons(symbol=board_name)
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    DataWarning(
                        source=f"{board_type}_board_cons",
                        message=f"failed to fetch constituents for {board_name}: {type(exc).__name__}: {exc}",
                    )
                )
                continue
            _add_board_constituents(candidates, cons, board_name, board_type, keywords)


def _add_board_constituents(
    candidates: dict[str, Candidate],
    frame: pd.DataFrame,
    board_name: str,
    board_type: str,
    keywords: list[str],
) -> None:
    code_col = _first_col(frame, ["代码", "股票代码", "证券代码", "f12"])
    name_col = _first_col(frame, ["名称", "股票名称", "证券简称", "f14"])
    if code_col is None or name_col is None:
        return
    matched = _matched_keywords(board_name, keywords) or [board_name]
    fetched_at = _now_iso()
    for _, row in frame.iterrows():
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not code or not name:
            continue
        provenance = [f"{board_type} board {board_name}"]
        candidate = candidates.get(code)
        if candidate is None:
            candidates[code] = Candidate(
                symbol=code,
                name=name,
                market_type=MarketType.A_SHARE,
                matched_theme=board_name,
                matched_keywords=matched,
                provenance=provenance,
                provider="eastmoney",
                fetched_at=fetched_at,
            )
        else:
            _merge_candidate(candidate, matched, provenance)


def _merge_candidate(candidate: Candidate, keywords: list[str], provenance: list[str]) -> None:
    for keyword in keywords:
        if keyword not in candidate.matched_keywords:
            candidate.matched_keywords.append(keyword)
    for item in provenance:
        if item not in candidate.provenance:
            candidate.provenance.append(item)


def _matched_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    lower_text = text.lower()
    result: list[str] = []
    for keyword in keywords:
        clean = keyword.strip()
        if not clean:
            continue
        if clean.lower() in lower_text or clean in text:
            result.append(clean)
    return result


def _first_col(frame: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
