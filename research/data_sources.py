"""Market data source helpers for the US-to-A-share research project."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import akshare as ak
import pandas as pd


@dataclass(frozen=True)
class MarketDataResult:
    provider: str
    data: pd.DataFrame


def _first_success(
    providers: list[tuple[str, Callable[[], pd.DataFrame]]],
) -> MarketDataResult:
    errors: list[str] = []
    for name, fetch in providers:
        try:
            data = fetch()
        except Exception as exc:  # noqa: BLE001 - provider fallback should be broad
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        if not data.empty:
            return MarketDataResult(provider=name, data=data)

        errors.append(f"{name}: empty dataframe")

    raise RuntimeError("All market data providers failed: " + " | ".join(errors))


def fetch_a_stock_spot() -> MarketDataResult:
    """Fetch A-share spot quotes, preferring Eastmoney for richer fields."""
    return _first_success(
        [
            ("eastmoney", ak.stock_zh_a_spot_em),
            ("sina", ak.stock_zh_a_spot),
        ]
    )


def fetch_etf_spot() -> MarketDataResult:
    """Fetch ETF spot data, preferring Eastmoney and falling back to THS."""
    return _first_success(
        [
            ("eastmoney", ak.fund_etf_spot_em),
            ("ths", ak.fund_etf_spot_ths),
        ]
    )
