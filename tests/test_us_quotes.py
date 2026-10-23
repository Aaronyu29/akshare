import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from stock_alert.us_quotes import USQuote, fetch_us_quote, fetch_us_quotes, us_session


class USQuotesTests(unittest.TestCase):
    def test_source_timestamp_is_separate_from_retrieval_time(self):
        quote = USQuote(
            "MU",
            873,
            "premarket",
            1792750920000,
            "fixture",
            quote_time="2026-10-23T06:22:00-04:00",
            fetched_at="2026-10-23T06:22:21-04:00",
            status="current",
        )
        self.assertNotEqual(
            quote.payload()["quote_time"], quote.payload()["fetched_at"]
        )
        self.assertEqual(quote.payload()["instrument_type"], "equity")

    def test_legacy_unavailable_option_performs_no_request(self):
        with patch("stock_alert.us_quotes.fetch_market_snapshot") as get:
            quote = fetch_us_quote("MU", session="overnight_unavailable")
        self.assertIsNone(quote.price)
        get.assert_not_called()

    def test_empty_batch_performs_no_request(self):
        with patch("stock_alert.market_quotes.fetch_market_snapshot") as get:
            self.assertEqual(fetch_us_quotes([]), [])
        get.assert_not_called()

    def test_friday_after_close_and_sunday_night_are_distinct(self):
        ny = ZoneInfo("America/New_York")
        self.assertEqual(us_session(datetime(2026, 10, 23, 22, tzinfo=ny)), "closed")
        self.assertEqual(us_session(datetime(2026, 10, 25, 22, tzinfo=ny)), "overnight")
