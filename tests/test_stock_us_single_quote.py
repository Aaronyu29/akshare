import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import akshare as ak
from akshare.stock.stock_us_sina import _parse_us_single_quote, _us_quote_time

MODULE = "akshare.stock.stock_us_sina"
NY = ZoneInfo("America/New_York")


def quote(
    extended_time="Oct 23 06:10AM EDT",
    regular_time="Oct 22 04:00PM EDT",
    extended_price="871.9182",
):
    fields = ["0"] * 28
    fields[0] = "Micron"
    fields[1], fields[2], fields[4] = "856.49", "-6.26", "-57.18"
    fields[21], fields[22], fields[23] = extended_price, "1.80", "15.43"
    fields[24], fields[25], fields[26] = extended_time, regular_time, "913.67"
    return 'var hq_str_gb_mu="' + ",".join(fields) + '";'


class SingleQuoteTests(unittest.TestCase):
    def test_premarket_selects_extended_price_and_source_time(self):
        row = _parse_us_single_quote(
            quote(), "MU", datetime(2026, 10, 23, 6, 11, tzinfo=NY)
        )
        self.assertEqual(row["price"], 871.9182)
        self.assertEqual(row["regular_price"], 856.49)
        self.assertEqual(row["quote_time"], "2026-10-23T06:10:00-04:00")
        self.assertEqual(row["quote_age_seconds"], 60)
        self.assertIsNone(row["error"])

    def test_after_hours_selects_extended_price(self):
        row = _parse_us_single_quote(
            quote(extended_time="Oct 23 05:00PM EDT"),
            "MU",
            datetime(2026, 10, 23, 17, 1, tzinfo=NY),
        )
        self.assertEqual(row["session"], "after_hours")
        self.assertEqual(row["price"], 871.9182)

    def test_regular_session_selects_regular_price(self):
        row = _parse_us_single_quote(
            quote(regular_time="Oct 23 10:00AM EDT"),
            "MU",
            datetime(2026, 10, 23, 10, 1, tzinfo=NY),
        )
        self.assertEqual(row["price"], 856.49)
        self.assertEqual(row["session"], "regular")

    def test_previous_day_and_wrong_session_are_not_current_quotes(self):
        for value in ("Oct 22 06:10AM EDT", "Oct 22 07:59PM EDT"):
            with self.subTest(value=value):
                row = _parse_us_single_quote(
                    quote(extended_time=value),
                    "MU",
                    datetime(2026, 10, 23, 6, 11, tzinfo=NY),
                )
                self.assertIsNone(row["price"])
                self.assertIsNotNone(row["error"])

    def test_stale_and_missing_extended_quotes_do_not_fall_back_to_close(self):
        for raw in (
            quote(extended_time="Oct 23 04:00AM EDT"),
            quote(extended_price="0"),
        ):
            row = _parse_us_single_quote(
                raw, "MU", datetime(2026, 10, 23, 6, 11, tzinfo=NY)
            )
            self.assertIsNone(row["price"])
            self.assertEqual(row["regular_price"], 856.49)

    def test_overnight_and_weekend_are_explicitly_unavailable(self):
        for now in (
            datetime(2026, 10, 23, 22, tzinfo=NY),
            datetime(2026, 10, 24, 6, tzinfo=NY),
        ):
            row = _parse_us_single_quote(quote(), "MU", now)
            self.assertIsNone(row["price"])
            self.assertIsNotNone(row["error"])

    def test_year_boundary(self):
        stamp = _us_quote_time("Dec 31 07:10PM EST", datetime(2027, 1, 1, 1, tzinfo=NY))
        self.assertEqual(stamp.year, 2026)
        self.assertEqual(stamp.utcoffset().total_seconds(), -18000)

    def test_single_query_sends_one_request_and_never_enters_pagination(self):
        response = Mock()
        response.text = quote()
        with (
            patch(MODULE + ".requests.get", return_value=response) as get,
            patch(
                MODULE + ".__get_us_page_count",
                side_effect=AssertionError("must not paginate"),
            ),
        ):
            frame = ak.stock_us_spot(symbol="mu", timeout=3)
        self.assertEqual(frame.iloc[0]["symbol"], "MU")
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"], {"list": "gb_mu"})
        self.assertEqual(get.call_args.kwargs["timeout"], 3)

    def test_invalid_symbols_and_bad_upstream_response_fail_clearly(self):
        with patch(MODULE + ".requests.get") as get:
            for value in ("", "MU,NVDA", "MU&list=other"):
                with self.assertRaises(ValueError):
                    ak.stock_us_spot(symbol=value)
            get.assert_not_called()
        for raw in ('var hq_str_gb_mu="";', 'var hq_str_gb_nvda="wrong";', "Forbidden"):
            with self.assertRaises(ValueError):
                _parse_us_single_quote(raw, "MU", datetime(2026, 10, 23, 6, tzinfo=NY))

    def test_no_argument_keeps_the_original_all_market_path(self):
        with (
            patch(MODULE + ".__get_us_page_count", return_value=0) as count,
            patch(MODULE + ".requests.get") as get,
        ):
            self.assertTrue(ak.stock_us_spot().empty)
            count.assert_called_once()
            get.assert_not_called()
