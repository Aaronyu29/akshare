"""Batch US session quotes using the official SDK's HTTP transport."""

from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime

from .longbridge_sdk import (
    LongbridgeError,
    build_config,
    official_credentials_available,
    read_quote_credentials,
    run_async,
    safe_error,
)

OfficialQuoteError = LongbridgeError
__all__ = [
    "fetch_official_quotes",
    "official_credentials_available",
    "read_quote_credentials",
]


def _epoch(value):
    # Naive SDK datetime values represent machine local time, not UTC.
    return value.timestamp() if isinstance(value, datetime) else value


def _period(item):
    if item is None:
        return None
    return {
        "price": str(item.last_done),
        "timestamp": _epoch(item.timestamp),
        "previous_close": str(item.prev_close),
        "volume": item.volume,
        "open": str(getattr(item, "open", "")),
        "high": str(item.high),
        "low": str(item.low),
        "turnover": str(item.turnover),
    }


def normalize_official_quote(item):
    return {
        "symbol": item.symbol.removesuffix(".US"),
        "currency": "USD",
        "trade_status": str(item.trade_status),
        "regular": _period(item),
        "premarket": _period(item.pre_market_quote),
        "after_hours": _period(item.post_market_quote),
        "overnight": _period(item.overnight_quote),
    }


async def _call_sdk(credentials, symbols, timeout):
    from longbridge.openapi import AsyncQuoteContext

    context = AsyncQuoteContext.create(build_config(credentials))
    values = []
    for start in range(0, len(symbols), 500):
        values.extend(
            await asyncio.wait_for(context.quote(symbols[start : start + 500]), timeout)
        )
        if start + 500 < len(symbols):
            await asyncio.sleep(0.12)
    return values


def fetch_official_quotes(symbols, *, timeout=6.0, credentials=None):
    unique = list(dict.fromkeys(s.strip().upper() for s in symbols))
    if not unique:
        return {}
    if (
        not math.isfinite(timeout)
        or timeout <= 0
        or any(not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.$][A-Z0-9]+)*", s) for s in unique)
    ):
        raise ValueError("Expected valid US tickers and a finite positive timeout")

    async def request():
        return await _call_sdk(
            credentials or read_quote_credentials(),
            [s + ".US" for s in unique],
            timeout,
        )

    try:
        raw = run_async(request)
        return {
            r["symbol"]: r
            for item in raw
            if (r := normalize_official_quote(item))["symbol"] in unique
        }
    except Exception as exc:
        raise safe_error(exc) from None
