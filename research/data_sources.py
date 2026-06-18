"""Market data source helpers for the US-to-A-share research project."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import akshare as ak
import pandas as pd

from .cache import (
    build_metadata,
    cache_path,
    load_dataframe_csv,
    save_dataframe_csv,
)
from .config import get_default_settings
from .schemas import DataWarning


@dataclass(frozen=True)
class MarketDataResult:
    provider: str
    data: pd.DataFrame
    fetched_at: str = field(default_factory=lambda: _now_iso())
    warnings: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return int(self.data.shape[0])


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
            return MarketDataResult(provider=name, data=data, warnings=tuple(errors))

        errors.append(f"{name}: empty dataframe")

    raise RuntimeError("All market data providers failed: " + " | ".join(errors))


def _cached_or_fetch(
    dataset: str,
    providers: list[tuple[str, Callable[[], pd.DataFrame]]],
    params: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
    use_cache: bool = True,
) -> MarketDataResult:
    settings = get_default_settings()
    ttl = ttl_seconds or settings.cache.spot_ttl_seconds
    params = params or {}

    if use_cache:
        for provider, _fetch in providers:
            path = cache_path(
                "normalized",
                provider,
                dataset,
                params=params,
                extension="csv",
                settings=settings.cache,
            )
            cached = load_dataframe_csv(path, require_fresh=True)
            if cached is not None and not cached.empty:
                return MarketDataResult(
                    provider=provider,
                    data=cached,
                    warnings=("loaded from cache",),
                )

    result = _first_success(providers)

    if use_cache:
        path = cache_path(
            "normalized",
            result.provider,
            dataset,
            params=params,
            extension="csv",
            settings=settings.cache,
        )
        metadata = build_metadata(
            provider=result.provider,
            dataset=dataset,
            params=params,
            ttl_seconds=ttl,
            row_count=result.row_count,
            settings=settings.cache,
        )
        save_dataframe_csv(path, result.data, metadata)

    return result


def fetch_a_stock_spot(use_cache: bool = True) -> MarketDataResult:
    """Fetch A-share spot quotes, preferring Eastmoney for richer fields."""
    return _cached_or_fetch(
        "a_stock_spot",
        providers=[
            ("eastmoney", ak.stock_zh_a_spot_em),
            ("sina", ak.stock_zh_a_spot),
        ],
        use_cache=use_cache,
    )


def fetch_etf_spot(use_cache: bool = True) -> MarketDataResult:
    """Fetch ETF spot data, preferring Eastmoney and falling back to THS."""
    return _cached_or_fetch(
        "etf_spot",
        providers=[
            ("eastmoney", ak.fund_etf_spot_em),
            ("ths", ak.fund_etf_spot_ths),
        ],
        use_cache=use_cache,
    )


def fetch_concept_board_names(use_cache: bool = True) -> MarketDataResult:
    """Fetch concept board names, preferring Eastmoney."""
    return _cached_or_fetch(
        "concept_board_names",
        providers=[
            ("eastmoney", ak.stock_board_concept_name_em),
            ("ths", ak.stock_board_concept_name_ths),
        ],
        ttl_seconds=get_default_settings().cache.board_ttl_seconds,
        use_cache=use_cache,
    )


def fetch_industry_board_names(use_cache: bool = True) -> MarketDataResult:
    """Fetch industry board names, preferring Eastmoney."""
    return _cached_or_fetch(
        "industry_board_names",
        providers=[
            ("eastmoney", ak.stock_board_industry_name_em),
            ("ths", ak.stock_board_industry_name_ths),
        ],
        ttl_seconds=get_default_settings().cache.board_ttl_seconds,
        use_cache=use_cache,
    )


def fetch_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    use_cache: bool = True,
) -> MarketDataResult:
    """Fetch A-share daily history with provider fallback."""
    symbol = symbol.strip()
    tx_symbol = _to_tx_symbol(symbol)
    sina_symbol = _to_sina_symbol(symbol)
    providers = [
        (
            "sina",
            lambda: ak.stock_zh_a_daily(
                symbol=sina_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            ),
        ),
        (
            "tencent",
            lambda: ak.stock_zh_a_hist_tx(
                symbol=tx_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            ),
        ),
    ]
    return _cached_or_fetch(
        "stock_history",
        providers=providers,
        params={"symbol": symbol, "start_date": start_date, "end_date": end_date},
        ttl_seconds=get_default_settings().cache.history_ttl_seconds,
        use_cache=use_cache,
    )


def fetch_etf_history(
    symbol: str,
    use_cache: bool = True,
) -> MarketDataResult:
    """Fetch ETF daily history from Sina."""
    normalized = _to_sina_etf_symbol(symbol)
    return _cached_or_fetch(
        "etf_history",
        providers=[("sina", lambda: ak.fund_etf_hist_sina(symbol=normalized))],
        params={"symbol": symbol},
        ttl_seconds=get_default_settings().cache.history_ttl_seconds,
        use_cache=use_cache,
    )


def fetch_etf_profile(symbol: str) -> MarketDataResult:
    """Fetch ETF profile data when AKShare exposes it; returns empty on failure."""
    try:
        data = ak.fund_etf_fund_info_em(fund=symbol)
    except TypeError:
        try:
            data = ak.fund_etf_fund_info_em(symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            warning = f"eastmoney etf profile failed: {type(exc).__name__}: {exc}"
            return MarketDataResult(
                provider="eastmoney",
                data=pd.DataFrame(),
                warnings=(warning,),
            )
    except Exception as exc:  # noqa: BLE001
        warning = f"eastmoney etf profile failed: {type(exc).__name__}: {exc}"
        return MarketDataResult(provider="eastmoney", data=pd.DataFrame(), warnings=(warning,))
    return MarketDataResult(provider="eastmoney", data=data)


def warnings_to_data_warnings(result: MarketDataResult, source: str) -> list[DataWarning]:
    return [
        DataWarning(source=source, message=warning)
        for warning in result.warnings
        if warning
    ]


def _to_sina_symbol(symbol: str) -> str:
    if symbol.startswith(("sh", "sz", "bj")):
        return symbol
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    if symbol.startswith(("0", "2", "3")):
        return f"sz{symbol}"
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return symbol


def _to_tx_symbol(symbol: str) -> str:
    return _to_sina_symbol(symbol)


def _to_sina_etf_symbol(symbol: str) -> str:
    if symbol.startswith(("sh", "sz")):
        return symbol
    if symbol.startswith(("5", "6")):
        return f"sh{symbol}"
    return f"sz{symbol}"
