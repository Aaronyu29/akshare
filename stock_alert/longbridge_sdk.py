"""Official Longbridge SDK access, sharing external credentials across contexts."""

from __future__ import annotations

import asyncio
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import cached_property
from pathlib import Path

DEFAULT_ENV_FILE = Path(r"C:\githubProject\.env-lark")


@dataclass(frozen=True)
class QuoteCredentials:
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    access_token: str = field(repr=False)


class LongbridgeError(RuntimeError):
    """Sanitized SDK failure; never includes response bodies or credentials."""


def read_quote_credentials(env_file=None, environ=None):
    from dotenv import dotenv_values

    env = os.environ if environ is None else environ
    path = Path(env_file or env.get("AKSHARE_QUOTE_ENV_FILE") or DEFAULT_ENV_FILE)
    values = (
        dotenv_values(path, interpolate=False, encoding="utf-8-sig")
        if path.is_file()
        else {}
    )

    def value(suffix, alias):
        names = ("LONGBRIDGE_" + suffix, "LONGPORT_" + suffix)
        # Generic aliases only apply to the explicitly selected file.
        for source, keys in ((env, names), (values, (*names, alias))):
            for key in keys:
                item = source.get(key)
                if item and item.strip():
                    return item.strip()
        return None

    key, secret, token = (
        value(s, a)
        for s, a in (
            ("APP_KEY", "APPKEY"),
            ("APP_SECRET", "AppSecretLong"),
            ("ACCESS_TOKEN", "AccessToken"),
        )
    )
    return QuoteCredentials(key, secret, token) if key and secret and token else None


def official_credentials_available():
    try:
        return read_quote_credentials() is not None
    except (OSError, UnicodeError, ImportError):
        return False


def build_config(credentials=None, *, env_file=None, streaming=False):
    from longbridge.openapi import Config, QuoteTransport

    credentials = credentials or read_quote_credentials(env_file)
    if credentials is None:
        raise LongbridgeError("Longbridge credentials are not configured")
    return Config.from_apikey(
        credentials.app_key,
        credentials.app_secret,
        credentials.access_token,
        http_url="https://openapi.longbridge.com",
        quote_ws_url="wss://openapi-quote.longbridge.com/v2",
        enable_overnight=True,
        enable_print_quote_packages=False,
        quote_transport=QuoteTransport.WebSocket if streaming else QuoteTransport.Http,
    )


def safe_error(exc):
    code = getattr(exc, "code", None)
    suffix = f", code={code}" if isinstance(code, int) else ""
    text = str(exc).lower()
    # Return fixed diagnostic labels, never the provider's response text.
    reason = ""
    if "only available in the us data center" in text:
        reason = ": endpoint unavailable for this account region"
    elif "permission" in text or "not authorized" in text:
        reason = ": account permission required"
    elif "internal server error" in text:
        reason = ": provider internal error"
    return LongbridgeError(
        f"Longbridge request failed ({type(exc).__name__}{suffix}){reason}"
    )


def run_async(factory):
    """Run an async request, including callers already running an event loop."""

    def run():
        return asyncio.run(factory())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(run).result()


# Documented overview names -> actual SDK 5.2.2 method names.
FUNDAMENTAL_METHODS = {
    "company_profile": "company",
    "financial_report": "financial_report",
    "valuations": "valuation",
    "dividends": "dividend",
    "fund_holdings": "fund_holder",
    "shareholders": "shareholder",
    "executives": "executive",
    "corp_action": "corp_action",
}
MARKET_METHODS = {
    "market_status": "market_status",
    "trading_stats": "trade_stats",
    "index_components": "constituent",
    "ah_premium": "ah_premium",
    "broker_positions": "broker_holding",
    "unusual_items": "anomaly",
}
CALENDAR_METHODS = {
    "earnings_calendar": "Report",
    "dividend_calendar": "Dividend",
    "ipo_calendar": "Ipo",
    "split_calendar": "Split",
    "macro_calendar": "MacroData",
}


class LongbridgeClient:
    """One credential/config entry point for all four official data contexts.

    Native contexts preserve SDK signatures and return types. ``query`` adds
    overview-name compatibility and a bounded asynchronous request timeout.
    """

    def __init__(self, *, env_file=None, credentials=None, timeout=10):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.timeout = timeout
        self._credentials = credentials or read_quote_credentials(env_file)
        if self._credentials is None:
            raise LongbridgeError("Longbridge credentials are not configured")

    @cached_property
    def config(self):
        return build_config(self._credentials)

    @cached_property
    def quotes(self):
        from longbridge.openapi import QuoteContext

        return QuoteContext(self.config)

    @cached_property
    def fundamentals(self):
        from longbridge.openapi import FundamentalContext

        return FundamentalContext(self.config)

    @cached_property
    def markets(self):
        from longbridge.openapi import MarketContext

        return MarketContext(self.config)

    @cached_property
    def calendars(self):
        from longbridge.openapi import CalendarContext

        return CalendarContext(self.config)

    def streaming_quotes(self):
        """Return a native WebSocket context for SDK subscribe/callback APIs."""
        from longbridge.openapi import QuoteContext

        return QuoteContext(build_config(self._credentials, streaming=True))

    def query(self, group, method, *args, **kwargs):
        """Read data through an async SDK context; return the native result.

        Groups: quote, fundamental, market, calendar. Calendar aliases take
        start/end YYYY-MM-DD, optional market/count/offset/next; preserve cursors.
        Enum parameters use SDK enum values (also accepted as exact enum names).
        """
        import longbridge.openapi as sdk

        contexts = {
            "quote": "AsyncQuoteContext",
            "fundamental": "AsyncFundamentalContext",
            "market": "AsyncMarketContext",
            "calendar": "AsyncCalendarContext",
        }
        if group not in contexts or method.startswith("_"):
            raise ValueError("Unknown data context or method")
        if group == "fundamental":
            method = FUNDAMENTAL_METHODS.get(method, method)
        elif group == "market":
            method = MARKET_METHODS.get(method, method)
        elif group == "calendar" and method in CALENDAR_METHODS:
            args = (getattr(sdk.CalendarCategory, CALENDAR_METHODS[method]), *args)
            method = "finance_calendar"
        # Restrict quote writes; native contexts still expose the full SDK.
        if group == "quote" and method in {
            "create_watchlist_group",
            "delete_watchlist_group",
            "update_watchlist_group",
            "update_pinned",
        }:
            raise ValueError("query only accepts read methods")
        cls = getattr(sdk, contexts[group])
        if (
            not hasattr(cls, method)
            or method in {"create"}
            or method.startswith("set_on_")
        ):
            raise ValueError("Unknown query method; see installed SDK signatures")
        enum_parameters = {
            ("financial_report", "kind"): "FinancialReportKind",
            ("financial_report", "period"): "FinancialReportPeriod",
            ("us_financial_statement", "kind"): "FinancialStatementKind",
            ("finance_calendar", "category"): "CalendarCategory",
            ("finance_calendar", "next"): "CalendarPageDirection",
            ("candlesticks", "period"): "Period",
            ("candlesticks", "adjust_type"): "AdjustType",
            ("history_candlesticks_by_date", "period"): "Period",
            ("history_candlesticks_by_date", "adjust_type"): "AdjustType",
        }
        for (name, parameter), enum_name in enum_parameters.items():
            if method == name and isinstance(kwargs.get(parameter), str):
                kwargs[parameter] = getattr(getattr(sdk, enum_name), kwargs[parameter])

        async def request():
            context = cls.create(self.config)
            return await asyncio.wait_for(
                getattr(context, method)(*args, **kwargs), self.timeout
            )

        try:
            return run_async(request)
        except Exception as exc:
            raise safe_error(exc) from None


def to_jsonable(value):
    """Convert SDK records without losing decimal precision or local timestamps."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if type(value).__module__ == "builtins" and hasattr(value, "__int__"):
        # PyO3 enum instances expose every enum member via dir(); traversing
        # those class constants would recurse forever.
        return str(value)
    fields = {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }
    return (
        {key: to_jsonable(item) for key, item in fields.items()}
        if fields
        else str(value)
    )


def main():
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Longbridge market and fundamental data via official SDK"
    )
    parser.add_argument("group", choices=("quote", "fundamental", "market", "calendar"))
    parser.add_argument("method")
    parser.add_argument(
        "--args", default="[]", help="JSON list of positional SDK arguments"
    )
    parser.add_argument(
        "--params", default="{}", help="JSON object of SDK keyword arguments"
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    try:
        positional, keywords = json.loads(args.args), json.loads(args.params)
        if not isinstance(positional, list) or not isinstance(keywords, dict):
            parser.error("--args must be an array; --params must be an object")
        value = LongbridgeClient(env_file=args.env_file, timeout=args.timeout).query(
            args.group, args.method, *positional, **keywords
        )
        print(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2))
    except LongbridgeError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
