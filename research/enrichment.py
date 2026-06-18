"""Candidate enrichment with market metrics."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from . import data_sources
from .schemas import Candidate, CandidateMetrics, DataWarning, EtfCandidate


def enrich_candidates(
    candidates: list[Candidate],
    etfs: list[EtfCandidate],
    use_live_data: bool = True,
) -> tuple[list[Candidate], list[EtfCandidate], list[DataWarning]]:
    warnings: list[DataWarning] = []
    if not use_live_data:
        warnings.append(DataWarning(source="enrichment", message="live enrichment disabled"))
        return candidates, etfs, warnings

    _enrich_stock_quotes(candidates, warnings)
    _enrich_stock_history(candidates, warnings)
    _enrich_etfs(etfs, warnings)
    return candidates, etfs, warnings


def _enrich_stock_quotes(candidates: list[Candidate], warnings: list[DataWarning]) -> None:
    try:
        result = data_sources.fetch_a_stock_spot()
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            DataWarning(source="a_stock_spot", message=f"quote enrichment failed: {exc}")
        )
        return
    frame = result.data
    code_col = _first_col(frame, ["代码", "code", "证券代码", "f12"])
    if code_col is None:
        return
    by_code = {str(row.get(code_col, "")).strip(): row for _, row in frame.iterrows()}
    for candidate in candidates:
        row = by_code.get(candidate.symbol)
        if row is None:
            continue
        candidate.metrics.latest_price = _pick_float(row, frame, ["最新价", "最新", "f2"])
        candidate.metrics.pct_change = _pick_float(row, frame, ["涨跌幅", "涨幅", "f3"])
        candidate.metrics.turnover_amount = _pick_float(row, frame, ["成交额", "amount", "f6"])
        candidate.metrics.volume = _pick_float(row, frame, ["成交量", "volume", "f5"])
        candidate.metrics.market_cap = _pick_float(row, frame, ["总市值", "f20"])
        candidate.metrics.pe = _pick_float(row, frame, ["市盈率-动态", "市盈率", "f9"])
        candidate.metrics.pb = _pick_float(row, frame, ["市净率", "f23"])


def _enrich_stock_history(candidates: list[Candidate], warnings: list[DataWarning]) -> None:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=80)).strftime("%Y%m%d")
    for candidate in candidates[:40]:
        try:
            result = data_sources.fetch_stock_history(candidate.symbol, start, end)
        except Exception as exc:  # noqa: BLE001
            candidate.data_warnings.append(
                DataWarning(
                    source="stock_history",
                    message=f"history enrichment failed: {type(exc).__name__}: {exc}",
                )
            )
            continue
        _attach_history_metrics(candidate.metrics, result.data)


def _enrich_etfs(etfs: list[EtfCandidate], warnings: list[DataWarning]) -> None:
    try:
        spot = data_sources.fetch_etf_spot()
    except Exception as exc:  # noqa: BLE001
        warnings.append(DataWarning(source="etf_spot", message=f"ETF enrichment failed: {exc}"))
        return
    frame = spot.data
    code_col = _first_col(frame, ["代码", "基金代码", "code", "f12"])
    if code_col is None:
        return
    by_code = {str(row.get(code_col, "")).strip(): row for _, row in frame.iterrows()}
    for etf in etfs:
        row = by_code.get(etf.code)
        if row is None:
            continue
        etf.turnover = etf.turnover or _pick_float(row, frame, ["成交额", "amount", "f6"])
        etf.fund_size = etf.fund_size or _pick_float(
            row,
            frame,
            ["总市值", "流通市值", "最新份额", "fund_size"],
        )
        discount = _pick_float(row, frame, ["基金折价率", "溢价率", "premium_discount"])
        etf.premium_discount = discount
        if not etf.management_fee:
            etf.management_fee = "pending verification"
        if not etf.custody_fee:
            etf.custody_fee = "pending verification"
        if not etf.tracking_index:
            etf.tracking_index = "pending verification"


def _attach_history_metrics(metrics: CandidateMetrics, frame: pd.DataFrame) -> None:
    close_col = _first_col(frame, ["close", "收盘", "收盘价"])
    volume_col = _first_col(frame, ["volume", "成交量", "amount"])
    if close_col is None or frame.empty:
        return
    closes = pd.to_numeric(frame[close_col], errors="coerce").dropna()
    if len(closes) < 2:
        return
    metrics.rsi = compute_rsi(closes)
    metrics.return_5d = _period_return(closes, 5)
    metrics.return_20d = _period_return(closes, 20)
    if volume_col is not None:
        volumes = pd.to_numeric(frame[volume_col], errors="coerce").dropna()
        if len(volumes) >= 20:
            recent = volumes.tail(5).mean()
            baseline = volumes.tail(20).head(15).mean()
            if baseline:
                metrics.volume_expansion = float(recent / baseline)
    if len(closes) >= 20:
        ma20 = closes.tail(20).mean()
        if ma20:
            metrics.ma_distance = float((closes.iloc[-1] - ma20) / ma20)


def compute_rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    delta = closes.diff().dropna()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.tail(period).mean()
    avg_loss = losses.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def _period_return(closes: pd.Series, period: int) -> float | None:
    if len(closes) <= period:
        return None
    base = closes.iloc[-period - 1]
    if base == 0:
        return None
    return float((closes.iloc[-1] - base) / base)


def _first_col(frame: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _pick_float(row: pd.Series, frame: pd.DataFrame, names: list[str]) -> float | None:
    col = _first_col(frame, names)
    if col is None:
        return None
    try:
        value = row.get(col)
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
