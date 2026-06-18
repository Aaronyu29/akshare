"""Market data source helpers for the US-to-A-share research project."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import akshare as ak
import pandas as pd
import requests

from .cache import (
    build_metadata,
    cache_path,
    load_dataframe_csv,
    save_dataframe_csv,
)
from .config import get_default_settings
from .schemas import DataWarning

EASTMONEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
}
EASTMONEY_CLIST_HOSTS = (
    "push2delay.eastmoney.com",
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "88.push2.eastmoney.com",
)
EASTMONEY_TIMEOUT_SECONDS = 8
EASTMONEY_PAGE_SIZE = 500


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
            actual_provider = name
            host = data.attrs.get("eastmoney_host")
            if host:
                actual_provider = f"{name}:{host}"
            eastmoney_errors = data.attrs.get("eastmoney_errors") or ()
            errors.extend(eastmoney_errors)
            return MarketDataResult(
                provider=actual_provider,
                data=data,
                warnings=tuple(errors),
            )

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
            ("eastmoney_direct", fetch_eastmoney_a_stock_spot_direct),
            ("eastmoney_akshare", ak.stock_zh_a_spot_em),
            ("sina", ak.stock_zh_a_spot),
        ],
        use_cache=use_cache,
    )


def fetch_etf_spot(use_cache: bool = True) -> MarketDataResult:
    """Fetch ETF spot data, preferring Eastmoney and falling back to THS."""
    return _cached_or_fetch(
        "etf_spot",
        providers=[
            ("eastmoney_direct", fetch_eastmoney_etf_spot_direct),
            ("eastmoney_akshare", ak.fund_etf_spot_em),
            ("ths", ak.fund_etf_spot_ths),
        ],
        use_cache=use_cache,
    )


def fetch_eastmoney_a_stock_spot_direct() -> pd.DataFrame:
    """Fetch A-share spot quotes from Eastmoney's current web clist endpoint."""
    params = {
        "pn": "1",
        "pz": str(EASTMONEY_PAGE_SIZE),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": (
            "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
            "f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152"
        ),
    }
    return _fetch_eastmoney_clist(params)


def fetch_eastmoney_etf_spot_direct() -> pd.DataFrame:
    """Fetch ETF spot quotes from Eastmoney's current web clist endpoint."""
    params = {
        "pn": "1",
        "pz": str(EASTMONEY_PAGE_SIZE),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "wbp2u": "|0|0|0|web",
        "fid": "f12",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024,b:MK0827",
        "fields": (
            "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,"
            "f12,f13,f14,f15,f16,f17,f18,f20,f21,"
            "f23,f24,f25,f22,f11,f30,f31,f32,f33,"
            "f34,f35,f38,f62,f63,f64,f65,f66,f69,"
            "f72,f75,f78,f81,f84,f87,f115,f124,f128,"
            "f136,f152,f184,f297,f402,f441"
        ),
    }
    return _fetch_eastmoney_clist(params)


def _fetch_eastmoney_clist(
    base_params: dict[str, str],
    hosts: tuple[str, ...] = EASTMONEY_CLIST_HOSTS,
) -> pd.DataFrame:
    errors: list[str] = []
    for host in hosts:
        try:
            frame = _fetch_eastmoney_clist_from_host(host, base_params)
        except Exception as exc:  # noqa: BLE001 - try every public web host
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
            continue
        if not frame.empty:
            frame.attrs["eastmoney_host"] = host
            frame.attrs["eastmoney_errors"] = tuple(errors)
            return frame
        errors.append(f"{host}: empty dataframe")
    raise RuntimeError("Eastmoney clist hosts failed: " + " | ".join(errors))


def _fetch_eastmoney_clist_from_host(
    host: str,
    base_params: dict[str, str],
) -> pd.DataFrame:
    url = f"https://{host}/api/qt/clist/get"
    first_params = {**base_params, "pn": "1"}
    first_json = _request_eastmoney_clist(url, first_params)
    data = first_json.get("data") or {}
    diff = data.get("diff") or []
    if not diff:
        return pd.DataFrame()

    frames = [pd.DataFrame(diff)]
    total = int(data.get("total") or len(diff))
    page_size = len(diff)
    total_pages = max(1, (total + page_size - 1) // page_size)
    for page in range(2, total_pages + 1):
        params = {**base_params, "pn": str(page)}
        page_json = _request_eastmoney_clist(url, params)
        page_data = page_json.get("data") or {}
        page_diff = page_data.get("diff") or []
        if page_diff:
            frames.append(pd.DataFrame(page_diff))
    frame = pd.concat(frames, ignore_index=True)
    if "f3" in frame.columns:
        frame["f3"] = pd.to_numeric(frame["f3"], errors="coerce")
        frame.sort_values(by=["f3"], ascending=False, inplace=True, ignore_index=True)
    return frame


def _request_eastmoney_clist(url: str, params: dict[str, str]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers=EASTMONEY_HEADERS,
        timeout=EASTMONEY_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("rc") not in (0, None):
        raise RuntimeError(f"Eastmoney rc={payload.get('rc')}")
    return payload


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
