import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from stock_alert import market_quotes as mq
from stock_alert.us_quotes import fetch_us_quote, fetch_us_quotes, us_session

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 23, 6, 25, tzinfo=NY)


def page(symbol="MU", active=201, moment=NOW, night=True):
    regular = moment.replace(hour=16, minute=0) - timedelta(days=1)
    ext = (
        moment
        if active in (201, 203)
        else moment.replace(hour=19, minute=59) - timedelta(days=1)
    )
    data = {
        "counter_id": "ST/US/" + symbol,
        "currency": "USD",
        "trade_status": active,
        "last_done": "856.49",
        "timestamp": str(int((moment if active == 202 else regular).timestamp())),
        "market_price": "872.30",
        "market_timestamp": str(int(ext.timestamp())),
        "latency": False,
        "support_overnight": night,
        "overnight_price": {
            "last_done": "876.50",
            "timestamp": str(
                int(
                    (
                        moment if active == 207 else moment.replace(hour=4, minute=0)
                    ).timestamp()
                )
            ),
        },
        "status_desc": {"status_desc": "Source market state"},
        "overnight_bid_depths": [{"price": "876.40"}],
        "overnight_ask_depths": [{"price": "876.60"}],
    }
    obj = {
        "queryKey": ["stock", "quote-overview", "ST/US/" + symbol, "detail"],
        "state": {"data": {"code": 0, "data": data}},
    }
    return (
        "<script>window.__TANSTACK_DEHYDRATED__.queries.push("
        + json.dumps(obj)
        + ")</script>"
    )


class MarketQuoteTests(unittest.TestCase):
    def setUp(self):
        mq._CACHE.clear()
        patched = patch.object(mq, "official_credentials_available", return_value=False)
        patched.start()
        self.addCleanup(patched.stop)

    def test_night_record_is_historical_during_premarket(self):
        result = mq.parse_longbridge(page(), "MU", NOW)
        self.assertEqual(result["quotes"]["premarket"]["status"], "current")
        night = result["quotes"]["overnight"]
        self.assertEqual(night["price"], 876.5)
        self.assertEqual(night["status"], "historical")
        self.assertEqual(night["quote_time_shanghai"], "2026-10-23T16:00:00+08:00")
        self.assertEqual(night["instrument_type"], "equity")

    def test_active_session_prices_come_from_the_correct_fields(self):
        for state, hour, session, price in (
            (201, 6, "premarket", 872.3),
            (202, 11, "regular", 856.49),
            (203, 17, "after_hours", 872.3),
            (207, 22, "overnight", 876.5),
        ):
            with self.subTest(session=session):
                now = NOW.replace(hour=hour)
                result = mq.parse_longbridge(page(active=state, moment=now), "MU", now)
                self.assertEqual(result["active_session"], session)
                self.assertEqual(result["quotes"][session]["price"], price)
                self.assertEqual(result["quotes"][session]["status"], "current")

    def test_missing_night_is_not_filled_with_close_or_token_price(self):
        now = NOW.replace(hour=22)
        result = mq.parse_longbridge(
            page(active=207, moment=now, night=False), "MU", now
        )
        self.assertIsNone(result["quotes"]["overnight"]["price"])
        self.assertEqual(result["quotes"]["overnight"]["status"], "unavailable")

    def test_source_time_not_fetch_time_and_staleness(self):
        result = mq.parse_longbridge(page(), "MU", NOW + timedelta(hours=1))
        quote = result["quotes"]["premarket"]
        self.assertEqual(quote["status"], "stale")
        self.assertEqual(quote["age_seconds"], 3600)
        future = mq.parse_longbridge(page(moment=NOW + timedelta(hours=1)), "MU", NOW)
        self.assertIsNone(future["quotes"]["premarket"]["price"])

    def test_symbol_and_currency_validation(self):
        for html in (
            page(symbol="NVDA"),
            page().replace('"USD"', '"HKD"'),
            "<script>alert(1)</script>",
        ):
            with self.assertRaises(ValueError):
                mq.parse_longbridge(html, "MU", NOW)

    def test_sina_unknown_delay_and_no_overnight_claim(self):
        row = {
            "symbol": "MU",
            "regular_price": 856.49,
            "regular_quote_time": "2026-10-22T16:00:00-04:00",
            "extended_price": 872.3,
            "extended_quote_time": NOW.isoformat(),
        }
        result = mq.parse_sina(row, "MU", NOW)
        self.assertEqual(result["quotes"]["premarket"]["price"], 872.3)
        self.assertIsNone(result["quotes"]["premarket"]["delayed"])
        self.assertIsNone(result["quotes"]["overnight"]["price"])

    def test_nasdaq_explicit_market_state_and_timestamp(self):
        payload = {
            "data": {
                "symbol": "MU",
                "marketStatus": "Pre-Market",
                "primaryData": {
                    "lastSalePrice": "$872.30",
                    "lastTradeTimestamp": "Oct 23, 2026 6:25 AM ET",
                    "isRealTime": True,
                    "bidPrice": "$872.20",
                },
                "secondaryData": {
                    "lastSalePrice": "$856.49",
                    "lastTradeTimestamp": "Closed at Oct 22, 2026 4:00 PM ET",
                },
            }
        }
        result = mq.parse_nasdaq(payload, "MU", NOW)
        self.assertEqual(
            result["quotes"]["premarket"]["timestamp_ms"], int(NOW.timestamp() * 1000)
        )
        self.assertFalse(result["quotes"]["premarket"]["delayed"])
        self.assertEqual(result["quotes"]["regular"]["status"], "historical")

    def test_auto_falls_back_without_market_pagination(self):
        calls = []

        def fake(symbol, source, *args):
            calls.append(source)
            if source == "akshare":
                raise ConnectionError("reset")
            return mq._snapshot(
                symbol,
                "premarket",
                "nasdaq-public",
                NOW,
                1200,
                {"premarket": (872.3, NOW.isoformat())},
            )

        with patch.object(mq, "_fetch_source", side_effect=fake):
            quote = fetch_us_quote("MU", now=NOW, retries=1)
        self.assertEqual(calls, ["akshare", "nasdaq"])
        self.assertEqual(quote.price, 872.3)
        self.assertEqual(quote.source, "nasdaq-public")

    def test_night_failure_never_uses_daytime_or_derivative_source(self):
        with patch.object(
            mq, "_fetch_source", side_effect=ConnectionError("reset")
        ) as get:
            quote = fetch_us_quote("MU", now=NOW.replace(day=22, hour=22), retries=1)
        self.assertEqual(get.call_count, 1)
        self.assertIsNone(quote.price)
        self.assertEqual(quote.session, "overnight")

    def test_explicit_previous_session_is_labelled_historical(self):
        result = mq.parse_longbridge(page(), "MU", NOW)
        with patch.object(mq, "_fetch_source", return_value=result):
            quote = fetch_us_quote("MU", session="overnight", now=NOW)
        self.assertEqual(quote.price, 876.5)
        self.assertEqual(quote.status, "historical")

    def test_provider_closed_state_overrides_wall_clock_estimate(self):
        result = mq.parse_longbridge(page(active=204), "MU", NOW)
        with patch.object(mq, "_fetch_source", return_value=result) as get:
            quote = fetch_us_quote("MU", now=NOW)
        self.assertEqual(quote.status, "closed")
        self.assertIsNone(quote.price)
        self.assertEqual(get.call_count, 1)

    def test_batch_deduplicates_preserves_order_and_isolates_failures(self):
        def fake(symbol, **kwargs):
            if symbol == "NVDA":
                raise TimeoutError("slow stock")
            result = mq.parse_longbridge(page(symbol), symbol, NOW)
            result.update(
                selected=result["quotes"]["premarket"], requested_session="auto"
            )
            return result

        with patch.object(mq, "fetch_market_snapshot", side_effect=fake):
            quotes = fetch_us_quotes(["nvda", "MU", "NVDA"], now=NOW)
        self.assertEqual([q.symbol for q in quotes], ["NVDA", "MU"])
        self.assertIsNone(quotes[0].price)
        self.assertEqual(quotes[1].price, 872.3)

    def test_live_success_is_cached_for_five_seconds(self):
        now = datetime.now(NY)
        snapshot = mq._snapshot(
            "MU", "regular", "fixture", now, 1200, {"regular": (123, now.isoformat())}
        )
        with patch.object(mq, "_fetch_source", return_value=snapshot) as get:
            first = mq.fetch_market_snapshot("MU", session="regular")
            second = mq.fetch_market_snapshot("MU", session="regular")
        self.assertEqual(get.call_count, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(
            second["selected"]["timestamp_ms"], int(now.timestamp() * 1000)
        )

    def test_weekend_sunday_night_dst_and_boundaries(self):
        cases = (
            (datetime(2026, 10, 23, 22, tzinfo=NY), "closed"),
            (datetime(2026, 10, 24, 12, tzinfo=NY), "closed"),
            (datetime(2026, 10, 25, 19, 59, tzinfo=NY), "closed"),
            (datetime(2026, 10, 25, 20, tzinfo=NY), "overnight"),
            (datetime(2026, 10, 26, 3, 59, tzinfo=NY), "overnight"),
            (datetime(2026, 10, 26, 4, tzinfo=NY), "premarket"),
            (datetime(2026, 10, 26, 9, 30, tzinfo=NY), "regular"),
            (datetime(2026, 10, 26, 16, tzinfo=NY), "after_hours"),
            (datetime(2026, 11, 2, 9, 30, tzinfo=NY), "regular"),
        )
        for stamp, expected in cases:
            self.assertEqual(us_session(stamp), expected)

    def test_input_validation_makes_no_network_request(self):
        with patch.object(mq, "_fetch_source") as get:
            for ticker in ("", "MU,NVDA", "MU&x=1"):
                with self.assertRaises(ValueError):
                    mq.fetch_market_snapshot(ticker)
            get.assert_not_called()

    def test_etf_counter_id_is_supported_without_confusing_it_with_a_stock(self):
        html = page(symbol="QQQ").replace("ST/US/QQQ", "ETF/US/QQQ")
        result = mq.parse_longbridge(html, "QQQ", NOW)
        self.assertEqual(result["quotes"]["overnight"]["price"], 876.5)
        self.assertEqual(result["quotes"]["premarket"]["instrument_type"], "etf")

    def test_all_sessions_prefers_the_source_with_real_night_fields(self):
        result = mq.parse_longbridge(page(), "MU", NOW)
        with patch.object(mq, "_fetch_source", return_value=result) as get:
            mq.fetch_market_snapshot("MU", now=NOW, include_sessions=True)
        self.assertEqual(get.call_args.args[1], "longbridge")

    def test_temporary_empty_public_page_is_retried_within_the_budget(self):
        result = mq.parse_longbridge(page(), "MU", NOW)
        with patch.object(
            mq,
            "_fetch_source",
            side_effect=[mq.IncompletePublicSnapshot("empty page"), result],
        ) as get:
            response = mq.fetch_market_snapshot(
                "MU", now=NOW, source="longbridge", retries=2
            )
        self.assertEqual(get.call_count, 2)
        self.assertEqual(response["selected"]["status"], "current")

    def test_holiday_and_early_close_use_the_exchange_calendar(self):
        self.assertEqual(us_session(datetime(2026, 11, 26, 12, tzinfo=NY)), "closed")
        self.assertEqual(
            us_session(datetime(2026, 11, 27, 12, 59, tzinfo=NY)), "regular"
        )
        self.assertEqual(
            us_session(datetime(2026, 11, 27, 13, tzinfo=NY)), "after_hours"
        )

    def test_closed_backup_overrides_an_earlier_stale_result(self):
        stale = mq.parse_longbridge(page(), "MU", NOW + timedelta(hours=1))
        closed = mq.parse_longbridge(page(active=204), "MU", NOW + timedelta(hours=1))
        with patch.object(mq, "_fetch_source", side_effect=[stale, closed]):
            result = mq.fetch_market_snapshot(
                "MU", now=NOW + timedelta(hours=1), retries=1
            )
        self.assertEqual(result["selected"]["status"], "closed")
        self.assertIsNone(result["selected"]["price"])
