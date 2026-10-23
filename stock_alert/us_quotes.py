"""Read-only US stock quotes across premarket, regular, postmarket and overnight."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from tabulate import tabulate

from .market_quotes import (
    MAJOR_SYMBOLS,
    PERIODS,
    fetch_market_snapshot,
    fetch_market_snapshots,
    session_at,
)

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class USQuote:
    symbol: str
    price: float | None
    session: str
    timestamp_ms: int | None
    source: str
    currency: str | None = "USD"
    error: str | None = None
    quote_time: str | None = None
    fetched_at: str | None = None
    status: str = "unavailable"
    age_seconds: float | None = None
    bid: float | None = None
    ask: float | None = None
    delayed: bool | None = None
    instrument_type: str = "equity"

    def payload(self):
        return asdict(self)


def us_session(now: datetime | None = None) -> str:
    """Estimate the time window; provider market state takes precedence."""
    return session_at(now or datetime.now(NEW_YORK))


def _selected(snapshot):
    row = snapshot["selected"]
    # The short API only exposes a price when current, or explicitly requested history.
    valid = row["status"] == "current" or (
        snapshot.get("requested_session") not in (None, "auto")
        and row["status"] == "historical"
    )
    return USQuote(
        symbol=snapshot["symbol"],
        price=row["price"] if valid else None,
        session=row["session"],
        timestamp_ms=row["timestamp_ms"],
        source=row["source"],
        currency=row["currency"],
        error=row.get("error"),
        quote_time=row["quote_time"],
        fetched_at=snapshot["fetched_at"],
        status=row["status"],
        age_seconds=row["age_seconds"],
        bid=row.get("bid"),
        ask=row.get("ask"),
        delayed=row.get("delayed"),
        instrument_type=row.get("instrument_type", "equity"),
    )


def fetch_us_quote(
    symbol: str,
    *,
    session=None,
    now=None,
    http=None,
    timeout=6.0,
    retries=2,
    source="auto",
    max_age=1200,
    use_cache=True,
):
    if session == "overnight_unavailable":
        return USQuote(
            symbol.strip().upper(),
            None,
            session,
            None,
            "unavailable",
            error="Legacy explicit overnight_unavailable request",
        )
    return _selected(
        fetch_market_snapshot(
            symbol,
            session=session,
            now=now,
            http=http,
            timeout=timeout,
            retries=retries,
            source=source,
            max_age=max_age,
            use_cache=use_cache,
        )
    )


def fetch_us_quotes(
    symbols: Iterable[str] = MAJOR_SYMBOLS,
    *,
    session=None,
    now=None,
    workers=6,
    timeout=6.0,
    source="auto",
    retries=2,
    max_age=1200,
    use_cache=True,
):
    return [
        _selected(snapshot)
        for snapshot in fetch_market_snapshots(
            symbols,
            session=session,
            now=now,
            workers=workers,
            timeout=timeout,
            source=source,
            retries=retries,
            max_age=max_age,
            use_cache=use_cache,
        )
    ]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="US equity quotes, with real source times and session labels"
    )
    parser.add_argument(
        "symbols",
        nargs="?",
        help="Comma-separated tickers; omitted uses 30 major stocks/ETFs",
    )
    parser.add_argument(
        "--session",
        choices=PERIODS,
        help="Request last-known quote for one session; may be historical",
    )
    parser.add_argument(
        "--all-sessions",
        action="store_true",
        help="Show each available last-known session separately",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "longbridge-api", "longbridge", "akshare", "nasdaq"),
        default="auto",
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=6)
    parser.add_argument("--max-age", type=float, default=1200)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--output", type=Path, help="Save full evidence as JSON")
    args = parser.parse_args()
    symbols = args.symbols.split(",") if args.symbols else MAJOR_SYMBOLS
    snapshots = fetch_market_snapshots(
        symbols,
        session=args.session,
        source=args.source,
        include_sessions=args.all_sessions,
        workers=args.workers,
        timeout=args.timeout,
        max_age=args.max_age,
        use_cache=not args.no_cache,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.format == "json":
        data = (
            snapshots
            if args.all_sessions
            else [quote.payload() for quote in map(_selected, snapshots)]
        )
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        periods = {
            "premarket": "盘前",
            "regular": "盘中",
            "after_hours": "盘后",
            "overnight": "夜盘",
            "closed": "休市",
            "halted": "停牌",
        }
        statuses = {
            "current": "当前有效",
            "historical": "历史记录",
            "stale": "已过期",
            "unavailable": "不可用",
            "closed": "休市",
        }
        sources = {
            "longbridge-openapi": "长桥官方 API",
            "akshare-sina": "AKShare/新浪",
            "longbridge-public": "长桥公开页",
            "nasdaq-public": "Nasdaq",
            "unavailable": "--",
        }
        display = []
        for snapshot in snapshots:
            rows = (
                snapshot["quotes"].values()
                if args.all_sessions
                else (snapshot["selected"],)
            )
            for row in rows:
                price = f"{row['price']:.4f}" if row["price"] is not None else "--"
                stamp = row["quote_time_shanghai"]
                stamp = (
                    datetime.fromisoformat(stamp).strftime("%Y-%m-%d %H:%M:%S")
                    if stamp
                    else "--"
                )
                status = statuses.get(row["status"], row["status"])
                if snapshot.get("cached"):
                    status += "（缓存）"
                display.append(
                    [
                        row["symbol"],
                        periods.get(row["session"], row["session"]),
                        price,
                        stamp,
                        status,
                        sources.get(row["source"], row["source"]),
                    ]
                )
        print(
            tabulate(
                display,
                headers=[
                    "代码",
                    "时段",
                    "价格 USD",
                    "行情时间（北京时间）",
                    "状态",
                    "来源",
                ],
                tablefmt="simple",
                disable_numparse=True,
            )
        )
        failures = [
            (s["symbol"], s["selected"].get("error"))
            for s in snapshots
            if s["selected"]["status"] not in ("current", "historical", "closed")
        ]
        for symbol, error in failures:
            print(f"{symbol}: {error or 'quote unavailable'}")


if __name__ == "__main__":
    main()
