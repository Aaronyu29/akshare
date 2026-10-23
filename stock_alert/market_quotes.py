"""Equity snapshots using the official SDK and public fallbacks."""

from __future__ import annotations

import copy
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import akshare as ak
import exchange_calendars
import requests

from .longbridge_quotes import fetch_official_quotes, official_credentials_available

NY = ZoneInfo("America/New_York")
SH = ZoneInfo("Asia/Shanghai")
_CALENDAR = exchange_calendars.get_calendar(
    "XNYS", start="2020-01-01", end="2035-12-31"
)
PERIODS = ("premarket", "regular", "after_hours", "overnight")
ETF_SYMBOLS = {"QQQ", "SPY", "SMH", "IWM"}
MAJOR_SYMBOLS = (
    "MU",
    "NVDA",
    "AMD",
    "AVGO",
    "TSM",
    "SNDK",
    "WDC",
    "STX",
    "INTC",
    "ARM",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "PLTR",
    "ORCL",
    "NFLX",
    "COIN",
    "CRCL",
    "MSTR",
    "JPM",
    "V",
    "LLY",
    "GLW",
    "QQQ",
    "SPY",
    "SMH",
    "IWM",
)
_CACHE: dict[tuple, tuple[float, dict]] = {}
_LOCK = threading.Lock()


class IncompletePublicSnapshot(ValueError):
    """A public page temporarily returned no embedded quote payload."""


def session_at(now: datetime) -> str:
    """NYSE day calendar plus a next-trading-day overnight estimate."""
    local = now.astimezone(NY)
    minute = local.hour * 60 + local.minute
    if minute < 240 or minute >= 1200:
        trade_date = local.date() + (
            timedelta(days=1) if minute >= 1200 else timedelta()
        )
        return "overnight" if _CALENDAR.is_session(str(trade_date)) else "closed"
    day = str(local.date())
    if not _CALENDAR.is_session(day):
        return "closed"
    opening = _CALENDAR.session_open(day).to_pydatetime().astimezone(NY)
    closing = _CALENDAR.session_close(day).to_pydatetime().astimezone(NY)
    if local < opening:
        return "premarket"
    if local < closing:
        return "regular"
    return "after_hours"


def _number(value: Any) -> float | None:
    try:
        result = float(str(value).replace("$", "").replace(",", ""))
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError):
        return None


def _stamp(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
            seconds = float(value)
            return datetime.fromtimestamp(
                seconds / 1000 if seconds > 1e11 else seconds, NY
            )
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(NY) if parsed.tzinfo else None
    except (ValueError, OSError, OverflowError):
        return None


def _quote(
    symbol,
    session,
    price,
    stamp,
    source,
    active,
    now,
    max_age,
    *,
    delayed=None,
    bid=None,
    ask=None,
    volume=None,
    previous_close=None,
    open=None,
    high=None,
    low=None,
    turnover=None,
):
    value, at = _number(price), _stamp(stamp)
    age = (now - at).total_seconds() if at else None
    error = None
    if value is None or at is None:
        value, status, error = (
            None,
            "unavailable",
            "No valid source price and timestamp",
        )
    elif age < -60:
        value, status, error = None, "unavailable", "Source timestamp is in the future"
    elif session != active:
        status = "historical"
    elif age > max_age:
        status, error = "stale", "Source quote is older than the freshness limit"
    else:
        status = "current"
    return {
        "symbol": symbol,
        "price": value,
        "currency": "USD",
        "session": session,
        "timestamp_ms": int(at.timestamp() * 1000) if at else None,
        "quote_time": at.isoformat() if at else None,
        "quote_time_shanghai": at.astimezone(SH).isoformat() if at else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "status": status,
        "source": source,
        "instrument_type": "etf" if symbol in ETF_SYMBOLS else "equity",
        "delayed": delayed,
        "bid": _number(bid),
        "ask": _number(ask),
        "volume": _nonnegative_number(volume),
        "previous_close": _number(previous_close),
        "open": _number(open),
        "high": _number(high),
        "low": _number(low),
        "turnover": _nonnegative_number(turnover),
        "error": error,
    }


def _snapshot(symbol, active, source, now, max_age, rows, **metadata):
    quotes = {
        period: _quote(symbol, period, None, None, source, active, now, max_age)
        for period in PERIODS
    }
    for period, values in rows.items():
        if period in quotes:
            quotes[period] = _quote(
                symbol,
                period,
                *values[:2],
                source,
                active,
                now,
                max_age,
                **(values[2] if len(values) > 2 else {}),
            )
    return {
        "symbol": symbol,
        "instrument_type": "etf" if symbol in ETF_SYMBOLS else "equity",
        "currency": "USD",
        "active_session": active,
        "source": source,
        "fetched_at": now.isoformat(),
        "quotes": quotes,
        **metadata,
    }


def parse_longbridge(html, symbol, now, max_age=1200):
    # Parse JSON arguments as data; never evaluate website JavaScript.
    marker = re.search(r"window\.__TANSTACK_DEHYDRATED__\.queries\.push\(", html)
    if not marker:
        raise IncompletePublicSnapshot(
            "Longbridge public page has no supported quote snapshot"
        )
    cursor, decoder, detail = marker.end(), json.JSONDecoder(), None
    while True:
        obj, cursor = decoder.raw_decode(html, cursor)
        key = obj.get("queryKey", [])
        envelope = obj.get("state", {}).get("data", {})
        data = envelope.get("data") if isinstance(envelope, dict) else None
        allowed = (
            ["stock", "quote-overview", prefix + symbol, "detail"]
            for prefix in ("ST/US/", "ETF/US/")
        )
        if key in allowed and isinstance(data, dict):
            detail = data
            break
        while cursor < len(html) and html[cursor].isspace():
            cursor += 1
        if cursor >= len(html) or html[cursor] != ",":
            break
        cursor += 1
        while html[cursor].isspace():
            cursor += 1
    if not detail or detail.get("counter_id") not in (
        "ST/US/" + symbol,
        "ETF/US/" + symbol,
    ):
        raise ValueError("Longbridge quote symbol mismatch or missing quote data")
    if detail.get("currency") != "USD":
        raise ValueError("Expected a USD equity quote")
    active = {
        201: "premarket",
        202: "regular",
        203: "after_hours",
        204: "closed",
        205: "halted",
        207: "overnight",
    }.get(detail.get("trade_status"), "unknown")
    rows = {
        "regular": (
            detail.get("last_done"),
            detail.get("timestamp"),
            {"delayed": detail.get("latency")},
        )
    }
    extended = _stamp(detail.get("market_timestamp"))
    if extended:
        period = "premarket" if extended.hour < 12 else "after_hours"
        rows[period] = (
            detail.get("market_price"),
            detail.get("market_timestamp"),
            {"delayed": detail.get("latency")},
        )
    overnight = detail.get("overnight_price") or {}
    if detail.get("support_overnight"):
        rows["overnight"] = (
            overnight.get("last_done"),
            overnight.get("timestamp"),
            {
                "bid": (detail.get("overnight_bid_depths") or [{}])[0].get("price"),
                "ask": (detail.get("overnight_ask_depths") or [{}])[0].get("price"),
                "volume": overnight.get("amount"),
            },
        )
    result = _snapshot(
        symbol,
        active,
        "longbridge-public",
        now,
        max_age,
        rows,
        overnight_supported=bool(detail.get("support_overnight")),
        market_state=detail.get("status_desc", {}).get("status_desc"),
        trade_status=detail.get("trade_status"),
        source_url="https://longbridge.com/quote/" + symbol + ".US",
    )
    if active in PERIODS:
        result["quotes"][active].update(
            bid=_number((detail.get("bid_depths") or [{}])[0].get("price")),
            ask=_number((detail.get("ask_depths") or [{}])[0].get("price")),
        )
        if active == "overnight":
            result["quotes"][active].update(
                bid=_number(
                    (detail.get("overnight_bid_depths") or [{}])[0].get("price")
                ),
                ask=_number(
                    (detail.get("overnight_ask_depths") or [{}])[0].get("price")
                ),
            )
    return result


def parse_sina(row, symbol, now, max_age=1200):
    if row.get("symbol") != symbol:
        raise ValueError("AKShare returned a different symbol")
    active = session_at(now)
    rows = {"regular": (row.get("regular_price"), row.get("regular_quote_time"))}
    extended = _stamp(row.get("extended_quote_time"))
    if extended:
        period = session_at(extended)
        if period in ("premarket", "after_hours"):
            rows[period] = (row.get("extended_price"), row.get("extended_quote_time"))
    return _snapshot(
        symbol, active, "akshare-sina", now, max_age, rows, overnight_supported=False
    )


def parse_nasdaq(payload, symbol, now, max_age=1200):
    data = payload.get("data") or {}
    if data.get("symbol") != symbol:
        raise ValueError("Nasdaq returned no matching equity quote")
    active = {
        "Pre-Market": "premarket",
        "Market Open": "regular",
        "Open": "regular",
        "After Hours": "after_hours",
        "After-Hours": "after_hours",
        "Closed": "closed",
    }.get(data.get("marketStatus"), "unknown")
    rows = {}
    for name in ("secondaryData", "primaryData"):
        entry = data.get(name) or {}
        text = (
            (entry.get("lastTradeTimestamp") or "")
            .replace("Closed at ", "")
            .removesuffix(" ET")
        )
        try:
            at = datetime.strptime(text, "%b %d, %Y %I:%M %p").replace(tzinfo=NY)
        except ValueError:
            continue
        period = "regular" if name == "secondaryData" or active == "closed" else active
        if period in PERIODS:
            rows[period] = (
                entry.get("lastSalePrice"),
                at.isoformat(),
                {
                    "delayed": not entry["isRealTime"]
                    if isinstance(entry.get("isRealTime"), bool)
                    else None,
                    "bid": entry.get("bidPrice"),
                    "ask": entry.get("askPrice"),
                    "volume": entry.get("volume"),
                },
            )
    return _snapshot(
        symbol,
        active,
        "nasdaq-public",
        now,
        max_age,
        rows,
        market_state=data.get("marketStatus"),
        overnight_supported=None,
    )


def _nonnegative_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_official_quote(record, symbol, now, max_age=1200):
    if record.get("symbol") != symbol or record.get("currency") != "USD":
        raise ValueError("Unexpected official quote symbol/currency")
    active = session_at(now)
    if record.get("trade_status") != "TradeStatus.Normal":
        active = "halted"
    rows = {}
    for period in PERIODS:
        item = record.get(period)
        if item:
            rows[period] = (
                item["price"],
                item["timestamp"],
                {
                    k: item.get(k)
                    for k in (
                        "volume",
                        "previous_close",
                        "open",
                        "high",
                        "low",
                        "turnover",
                    )
                },
            )
    return _snapshot(
        symbol,
        active,
        "longbridge-openapi",
        now,
        max_age,
        rows,
        trade_status=record.get("trade_status"),
        enable_overnight=True,
    )


def _fetch_source(symbol, source, client, timeout, now, max_age):
    if source == "longbridge-api":
        records = fetch_official_quotes([symbol], timeout=timeout)
        if symbol not in records:
            raise ValueError("Official API returned no quote for this ticker")
        return parse_official_quote(
            records[symbol], symbol, now or datetime.now(NY), max_age
        )
    if source == "akshare":
        return parse_sina(
            ak.stock_us_spot(symbol=symbol, timeout=timeout).iloc[0].to_dict(),
            symbol,
            now or datetime.now(NY),
            max_age,
        )
    if source == "longbridge":
        response = client.get(
            "https://longbridge.com/quote/" + symbol + ".US",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        return parse_longbridge(response.text, symbol, now or datetime.now(NY), max_age)
    if source == "nasdaq":
        response = client.get(
            "https://api.nasdaq.com/api/quote/" + symbol + "/info",
            params={"assetclass": "stocks"},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.nasdaq.com/",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return parse_nasdaq(response.json(), symbol, now or datetime.now(NY), max_age)
    raise ValueError("Unknown equity quote source")


def fetch_market_snapshot(
    symbol: str,
    *,
    session: str | None = None,
    source="auto",
    now=None,
    http=None,
    timeout=6.0,
    retries=2,
    max_age=1200,
    use_cache=True,
    include_sessions=False,
    _official_batch=None,
    _official_error=None,
):
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.$][A-Z0-9]+)*", symbol):
        raise ValueError("Expected one US equity ticker")
    if source not in ("auto", "akshare", "longbridge", "nasdaq", "longbridge-api"):
        raise ValueError("Unknown source")
    if session is not None and session not in PERIODS:
        raise ValueError("Unknown session")
    if timeout <= 0 or max_age <= 0:
        raise ValueError("timeout and max_age must be positive")
    moment = (now or datetime.now(NY)).astimezone(NY)
    requested = session or session_at(moment)
    key = (symbol, session or requested, source, max_age, include_sessions)
    if use_cache and now is None and http is None:
        with _LOCK:
            cached = _CACHE.get(key)
            if cached and time.monotonic() - cached[0] < 5:
                result = copy.deepcopy(cached[1])
                at = _stamp(result["selected"]["timestamp_ms"])
                if at and (moment - at).total_seconds() <= max_age:
                    result["cached"] = True
                    result["cache_age_seconds"] = round(time.monotonic() - cached[0], 3)
                    for quote in result["quotes"].values():
                        stamp = _stamp(quote["timestamp_ms"])
                        if stamp:
                            quote["age_seconds"] = round(
                                (moment - stamp).total_seconds(), 3
                            )
                    selected_stamp = _stamp(result["selected"]["timestamp_ms"])
                    result["selected"]["age_seconds"] = round(
                        (moment - selected_stamp).total_seconds(), 3
                    )
                    return result
    if source != "auto":
        sources = (source,)
    elif include_sessions or requested == "overnight":
        sources = ("longbridge", "akshare", "nasdaq")
    else:
        sources = ("akshare", "nasdaq", "longbridge")
    if source == "auto" and (
        _official_batch is not None
        or _official_error is not None
        or official_credentials_available()
    ):
        sources = ("longbridge-api", *sources)
    attempts, best = [], None
    client = http or requests.Session()
    try:
        for provider in sources:
            if requested == "overnight" and provider in ("akshare", "nasdaq"):
                continue
            snapshot = None
            for attempt in range(max(1, retries)):
                try:
                    if provider == "longbridge-api" and _official_error is not None:
                        raise ValueError(_official_error)
                    if provider == "longbridge-api" and _official_batch is not None:
                        if symbol not in _official_batch:
                            raise ValueError(
                                "Official API returned no quote for this ticker"
                            )
                        snapshot = parse_official_quote(
                            _official_batch[symbol], symbol, moment, max_age
                        )
                    else:
                        snapshot = _fetch_source(
                            symbol, provider, client, timeout, now, max_age
                        )
                    break
                except Exception as exc:
                    attempts.append(
                        {
                            "source": provider,
                            "attempt": attempt + 1,
                            "error": type(exc).__name__ + ": " + str(exc)[:350],
                        }
                    )
                    if isinstance(exc, ValueError) and not isinstance(
                        exc, IncompletePublicSnapshot
                    ):
                        break
                    if attempt + 1 < max(1, retries):
                        time.sleep(0.2 * (attempt + 1))
            if snapshot is None:
                continue
            wanted = session or snapshot["active_session"]
            selected = snapshot["quotes"].get(wanted)
            if selected is None:
                selected = _quote(
                    symbol,
                    wanted,
                    None,
                    None,
                    snapshot["source"],
                    snapshot["active_session"],
                    moment,
                    max_age,
                )
                selected.update(
                    status="closed" if wanted == "closed" else "unavailable",
                    error="Market is closed or halted"
                    if wanted in ("closed", "halted")
                    else "Unknown trading session",
                )
            snapshot.update(
                selected=selected, requested_session=session or "auto", cached=False
            )
            if (
                best is None
                or selected["status"] in ("current", "historical", "closed")
                or snapshot["active_session"] == "halted"
            ):
                best = snapshot
            if (
                selected["status"] in ("current", "historical", "closed")
                or snapshot["active_session"] == "halted"
            ):
                break
            attempts.append(
                {
                    "source": provider,
                    "error": selected.get("error") or selected["status"],
                }
            )
    finally:
        if http is None:
            client.close()
    if best is None:
        best = _snapshot(symbol, session_at(moment), "unavailable", moment, max_age, {})
        best.update(
            selected=_quote(
                symbol,
                requested,
                None,
                None,
                "unavailable",
                best["active_session"],
                moment,
                max_age,
            ),
            requested_session=session or "auto",
            cached=False,
        )
    best["attempts"] = attempts
    if (
        use_cache
        and now is None
        and http is None
        and best["selected"]["status"] == "current"
    ):
        with _LOCK:
            _CACHE[key] = (time.monotonic(), copy.deepcopy(best))
    return best


def fetch_market_snapshots(
    symbols: Iterable[str] = MAJOR_SYMBOLS, *, workers=6, **kwargs
):
    unique = list(
        dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
    )
    if not unique:
        return []
    source = kwargs.get("source", "auto")
    if source == "longbridge-api" or (
        source == "auto" and official_credentials_available()
    ):
        try:
            kwargs["_official_batch"] = fetch_official_quotes(
                unique, timeout=kwargs.get("timeout", 6)
            )
        except Exception as exc:
            kwargs["_official_error"] = type(exc).__name__ + ": " + str(exc)
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(unique)))) as pool:
        futures = {
            pool.submit(fetch_market_snapshot, symbol, **kwargs): symbol
            for symbol in unique
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as exc:
                moment = (kwargs.get("now") or datetime.now(NY)).astimezone(NY)
                result = _snapshot(
                    symbol,
                    session_at(moment),
                    "unavailable",
                    moment,
                    kwargs.get("max_age", 1200),
                    {},
                )
                result["selected"] = _quote(
                    symbol,
                    kwargs.get("session") or result["active_session"],
                    None,
                    None,
                    "unavailable",
                    result["active_session"],
                    moment,
                    1200,
                )
                result["selected"]["error"] = type(exc).__name__ + ": " + str(exc)
                result["attempts"] = []
                results[symbol] = result
    return [results[symbol] for symbol in unique]
