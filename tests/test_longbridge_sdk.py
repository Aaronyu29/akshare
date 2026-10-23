import asyncio
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from stock_alert import longbridge_quotes as lq
from stock_alert import longbridge_sdk as ls
from stock_alert import market_quotes as mq

NOW = datetime(2026, 10, 23, 7, 0, tzinfo=ZoneInfo("America/New_York"))
CREDS = ls.QuoteCredentials("dummy-key", "dummy-secret", "dummy-token")


def raw_quote(symbol="TSM"):
    period = dict(
        last_done=Decimal("414.64"),
        prev_close=Decimal("412.35"),
        timestamp=datetime.fromtimestamp(NOW.timestamp()),
        volume=0,
        high=Decimal("420"),
        low=Decimal("410"),
        turnover=Decimal("0"),
    )
    return SimpleNamespace(
        symbol=symbol + ".US",
        trade_status="TradeStatus.Normal",
        pre_market_quote=SimpleNamespace(**period),
        post_market_quote=None,
        overnight_quote=None,
        **period,
    )


class CredentialsTests(unittest.TestCase):
    def test_file_aliases_bom_literals_and_no_lark_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / ".env"
            file.write_text(
                "APPKEY=file-key\nAppSecretLong='${LITERAL}'\nAccessToken=file-token\nAPPSecret=lark-secret\n",
                encoding="utf-8-sig",
            )
            creds = ls.read_quote_credentials(file, {})
            self.assertEqual(creds.app_secret, "${LITERAL}")
            self.assertEqual(creds.app_key, "file-key")
            overridden = ls.read_quote_credentials(
                file,
                {
                    "LONGBRIDGE_APP_KEY": "env-key",
                    "LONGBRIDGE_APP_SECRET": "env-secret",
                    "LONGBRIDGE_ACCESS_TOKEN": "env-token",
                },
            )
            self.assertEqual(overridden.app_key, "env-key")
            self.assertNotIn("file-token", repr(creds))
            file.write_text(
                "APPKEY=x\nAPPSecret=lark-secret\nAccessToken=y", encoding="utf-8"
            )
            with self.assertRaises(ls.LongbridgeError):
                ls.read_quote_credentials(file, {})

    def test_generic_environment_aliases_are_ignored(self):
        with tempfile.TemporaryDirectory():
            self.assertIsNone(
                ls.read_quote_credentials(
                    None,
                    {
                        "APPKEY": "x",
                        "AppSecretLong": "y",
                        "AccessToken": "z",
                    },
                )
            )

    def test_standard_and_legacy_environment_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            for prefix in ("LONGBRIDGE_", "LONGPORT_"):
                values = {
                    prefix + suffix: suffix
                    for suffix in ("APP_KEY", "APP_SECRET", "ACCESS_TOKEN")
                }
                creds = ls.read_quote_credentials(Path(folder) / "missing", values)
                self.assertEqual(creds.app_key, "APP_KEY")

    def test_config_enables_overnight_and_http(self):
        with patch("longbridge.openapi.Config") as config:
            ls.build_config(CREDS)
            kwargs = config.from_apikey.call_args.kwargs
            self.assertTrue(kwargs["enable_overnight"])
            self.assertEqual(kwargs["http_url"], "https://openapi.longbridge.com")
            from longbridge.openapi import QuoteTransport

            self.assertEqual(kwargs["quote_transport"], QuoteTransport.Http)

    def test_default_never_searches_host_files_or_working_directory(self):
        with patch.object(
            Path, "is_file", side_effect=AssertionError("must not probe host paths")
        ):
            self.assertIsNone(ls.read_quote_credentials(environ={}))

    def test_incomplete_environment_does_not_merge_with_file_or_legacy(self):
        with self.assertRaisesRegex(ls.LongbridgeError, "Incomplete"):
            ls.read_quote_credentials(
                environ={
                    "LONGBRIDGE_APP_KEY": "partial-key",
                    "LONGPORT_APP_KEY": "legacy-key",
                    "LONGPORT_APP_SECRET": "secret",
                    "LONGPORT_ACCESS_TOKEN": "token",
                    "AKSHARE_QUOTE_ENV_FILE": "/should/not/read",
                }
            )

    def test_mounted_secret_files_and_errors_are_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for suffix in ("APP_KEY", "APP_SECRET", "ACCESS_TOKEN"):
                path = Path(folder) / suffix
                path.write_text("private-value-" + suffix + "\n", encoding="utf-8")
                paths["LONGBRIDGE_" + suffix + "_FILE"] = str(path)
            creds = ls.read_quote_credentials(environ=paths)
            self.assertEqual(creds.access_token, "private-value-ACCESS_TOKEN")
            with self.assertRaisesRegex(ls.LongbridgeError, "only one"):
                ls.read_quote_credentials(
                    environ={**paths, "LONGBRIDGE_APP_KEY": "secret"}
                )
            paths["LONGBRIDGE_APP_KEY_FILE"] = str(Path(folder) / "secret-private-path")
            with self.assertRaises(ls.LongbridgeError) as caught:
                ls.read_quote_credentials(environ=paths)
            self.assertNotIn("secret-private-path", str(caught.exception))

    def test_missing_explicit_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ls.LongbridgeError):
                ls.read_quote_credentials(Path(folder) / "missing", {})


class OfficialQuoteTests(unittest.TestCase):
    def test_naive_sdk_time_preserves_epoch_on_every_host_timezone(self):
        row = lq.normalize_official_quote(raw_quote())
        self.assertEqual(row["premarket"]["timestamp"], NOW.timestamp())
        snapshot = mq.parse_official_quote(row, "TSM", NOW)
        self.assertEqual(snapshot["quotes"]["premarket"]["status"], "current")
        self.assertEqual(snapshot["quotes"]["premarket"]["volume"], 0)
        self.assertEqual(snapshot["quotes"]["premarket"]["turnover"], 0)
        self.assertEqual(
            snapshot["quotes"]["premarket"]["quote_time_shanghai"],
            "2026-10-23T19:00:00+08:00",
        )
        self.assertIsNone(snapshot["quotes"]["overnight"]["price"])

    def test_actual_sdk_boundary_receives_one_batch(self):
        with patch.object(
            lq,
            "_call_sdk",
            new=AsyncMock(
                return_value=[raw_quote(), raw_quote("MU"), raw_quote("OTHER")]
            ),
        ) as call:
            rows = lq.fetch_official_quotes(["tsm", "MU", "TSM"], credentials=CREDS)
            self.assertEqual(list(rows), ["TSM", "MU"])
            self.assertEqual(call.call_args.args[1], ["TSM.US", "MU.US"])
            self.assertEqual(call.call_count, 1)

    def test_errors_never_contain_provider_secret(self):
        with patch.object(
            lq, "_call_sdk", new=AsyncMock(side_effect=RuntimeError("dummy-token"))
        ):
            with self.assertRaises(ls.LongbridgeError) as caught:
                lq.fetch_official_quotes(["TSM"], credentials=CREDS)
            self.assertNotIn("dummy-token", str(caught.exception))

    def test_works_inside_an_existing_async_loop(self):
        async def caller():
            return lq.fetch_official_quotes(["TSM"], credentials=CREDS)

        with patch.object(lq, "_call_sdk", new=AsyncMock(return_value=[raw_quote()])):
            self.assertIn("TSM", asyncio.run(caller()))

    def test_thirty_symbols_one_call_and_no_public_requests(self):
        records = {
            symbol: lq.normalize_official_quote(raw_quote(symbol))
            for symbol in mq.MAJOR_SYMBOLS
        }
        with (
            patch.object(mq, "official_credentials_available", return_value=True),
            patch.object(mq, "fetch_official_quotes", return_value=records) as batch,
            patch.object(mq, "_fetch_source") as public,
        ):
            rows = mq.fetch_market_snapshots(now=NOW, use_cache=False)
            self.assertEqual(len(rows), 30)
            self.assertTrue(all(row["source"] == "longbridge-openapi" for row in rows))
            self.assertEqual(batch.call_count, 1)
            public.assert_not_called()

    def test_explicit_official_error_has_no_public_fallback(self):
        with (
            patch.object(
                mq,
                "fetch_official_quotes",
                side_effect=ls.LongbridgeError("safe error"),
            ) as batch,
            patch.object(mq, "_fetch_source") as public,
        ):
            rows = mq.fetch_market_snapshots(
                ["TSM", "MU"], source="longbridge-api", now=NOW
            )
            self.assertTrue(all(r["selected"]["price"] is None for r in rows))
            self.assertEqual(batch.call_count, 1)
            public.assert_not_called()

    def test_missing_symbol_falls_back_without_repeating_official_call(self):
        row = lq.normalize_official_quote(raw_quote())
        fallback = mq.parse_official_quote(
            lq.normalize_official_quote(raw_quote("MU")), "MU", NOW
        )
        fallback["source"] = "fake-public"
        with (
            patch.object(mq, "official_credentials_available", return_value=True),
            patch.object(
                mq, "fetch_official_quotes", return_value={"TSM": row}
            ) as batch,
            patch.object(mq, "_fetch_source", return_value=fallback) as public,
        ):
            result = mq.fetch_market_snapshots(["TSM", "MU"], now=NOW, use_cache=False)
            self.assertEqual(batch.call_count, 1)
            self.assertEqual(public.call_count, 1)
            self.assertEqual(result[1]["source"], "fake-public")

    def test_halt_wrong_symbol_and_invalid_input(self):
        row = lq.normalize_official_quote(raw_quote())
        row["trade_status"] = "TradeStatus.Halted"
        self.assertEqual(
            mq.parse_official_quote(row, "TSM", NOW)["active_session"], "halted"
        )
        with self.assertRaises(ValueError):
            mq.parse_official_quote(row, "MU", NOW)
        for ticker in ("TSM.US/secret", "../../secret"):
            with self.assertRaises(ValueError):
                lq.fetch_official_quotes([ticker], credentials=CREDS)
        for timeout in (float("inf"), float("nan"), 0):
            with self.assertRaises(ValueError):
                lq.fetch_official_quotes(["TSM"], credentials=CREDS, timeout=timeout)

    def test_chunking_above_sdk_500_limit(self):
        context = SimpleNamespace(quote=AsyncMock(return_value=[]))
        with (
            patch("longbridge.openapi.AsyncQuoteContext") as cls,
            patch.object(lq, "build_config"),
        ):
            cls.create.return_value = context
            asyncio.run(lq._call_sdk(CREDS, [f"S{i}.US" for i in range(501)], 1))
            self.assertEqual(
                [len(c.args[0]) for c in context.quote.call_args_list], [500, 1]
            )


class ContextTests(unittest.TestCase):
    def client(self):
        client = ls.LongbridgeClient(credentials=CREDS, timeout=0.05)
        client.config = object()
        return client

    def test_all_overview_fundamental_and_market_aliases(self):
        client = self.client()
        for group, cls_name, methods in (
            ("fundamental", "AsyncFundamentalContext", ls.FUNDAMENTAL_METHODS),
            ("market", "AsyncMarketContext", ls.MARKET_METHODS),
        ):
            for alias, native in methods.items():
                with self.subTest(alias=alias):
                    function = AsyncMock(return_value={"ok": True})
                    cls = SimpleNamespace(
                        create=lambda config: SimpleNamespace(**{native: function}),
                        **{native: function},
                    )
                    with patch("longbridge.openapi." + cls_name, cls):
                        self.assertEqual(
                            client.query(group, alias, "TSM.US"), {"ok": True}
                        )
                        function.assert_awaited_once_with("TSM.US")

    def test_all_calendar_aliases_preserve_pagination(self):
        client = self.client()
        function = AsyncMock(return_value={"next_date": "2026-10-25"})
        cls = SimpleNamespace(
            create=lambda config: SimpleNamespace(finance_calendar=function),
            finance_calendar=function,
        )
        import longbridge.openapi as sdk

        with patch("longbridge.openapi.AsyncCalendarContext", cls):
            for alias, category in ls.CALENDAR_METHODS.items():
                result = client.query(
                    "calendar",
                    alias,
                    "2026-10-23",
                    "2026-10-30",
                    market="US",
                    count=3,
                    offset=0,
                )
                self.assertEqual(result["next_date"], "2026-10-25")
                self.assertEqual(
                    function.call_args.args[0], getattr(sdk.CalendarCategory, category)
                )

    def test_enum_conversion_and_timeout(self):
        client = self.client()

        async def slow(*args, **kwargs):
            await asyncio.sleep(1)

        cls = SimpleNamespace(
            create=lambda config: SimpleNamespace(financial_report=slow),
            financial_report=slow,
        )
        with patch("longbridge.openapi.AsyncFundamentalContext", cls):
            with self.assertRaisesRegex(ls.LongbridgeError, "TimeoutError"):
                client.query(
                    "fundamental",
                    "financial_report",
                    "TSM.US",
                    kind="IncomeStatement",
                    period="Annual",
                )

    def test_native_query_read_guard_and_diagnostic_categories(self):
        client = self.client()
        for group, method in (
            ("trade", "submit_order"),
            ("quote", "create_watchlist_group"),
            ("fundamental", "_private"),
            ("quote", "create"),
        ):
            with self.assertRaises(ValueError):
                client.query(group, method)
        error = ls.safe_error(
            RuntimeError("only available in the US data center token=dummy-token")
        )
        self.assertIn("account region", str(error))
        self.assertNotIn("dummy-token", str(error))

    def test_decimal_and_sdk_local_time_json_serialization(self):
        from longbridge.openapi import TradeStatus

        self.assertEqual(ls.to_jsonable(TradeStatus.Normal), "TradeStatus.Normal")
        result = ls.to_jsonable(
            SimpleNamespace(
                price=Decimal("1.2300"),
                timestamp=datetime.fromtimestamp(NOW.timestamp()),
                empty=None,
                nested={"list": [Decimal("2.00")]},
            )
        )
        self.assertEqual(result["price"], "1.2300")
        self.assertEqual(
            datetime.fromisoformat(result["timestamp"]).timestamp(), NOW.timestamp()
        )
        self.assertEqual(result["nested"]["list"], ["2.00"])


if __name__ == "__main__":
    unittest.main()
