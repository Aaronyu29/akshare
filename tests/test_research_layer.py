from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import requests

from research.cache import (
    build_metadata,
    cache_path,
    load_json,
    save_json,
)
from research.cli import main as cli_main
from research.config import CacheSettings, get_default_settings
from research.data_sources import (
    _fetch_eastmoney_clist,
    _first_success,
    fetch_eastmoney_a_stock_spot_direct,
)
from research.filters import apply_filters
from research.pipeline import build_trigger_packet, run_research
from research.report import render_markdown_report
from research.schemas import (
    Candidate,
    CandidateEvidence,
    EvidenceTier,
    EtfCandidate,
    ResearchReport,
    ResearchRequest,
)
from research.scoring import score_candidate
from research.tools.scoring_tools import tool_score_candidate


class ResearchLayerTest(unittest.TestCase):
    def test_default_settings_capture_strategy_constraints(self) -> None:
        settings = get_default_settings()

        self.assertEqual(settings.market_scope, ("a_share", "etf"))
        self.assertIn("bse", settings.hard_excluded_boards)
        self.assertEqual(settings.core_candidate_target, 3)
        self.assertEqual(settings.max_core_candidates, 8)
        self.assertLess(settings.score_weights.min_risk_penalty, 0)

    def test_cache_json_round_trip_and_freshness(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = CacheSettings(
                cache_dir=root,
                raw_dir=root / "raw",
                normalized_dir=root / "normalized",
                evidence_dir=root / "evidence",
            )
            path = cache_path(
                "raw",
                "unit",
                "sample",
                {"symbol": "NVDA", "keywords": ["HBM", "cooling"]},
                extension="json",
                settings=settings,
            )
            metadata = build_metadata(
                provider="unit",
                dataset="sample",
                params={"symbol": "NVDA"},
                ttl_seconds=3600,
                row_count=1,
                settings=settings,
            )

            save_json(path, {"ok": True}, metadata)

            self.assertEqual(load_json(path, require_fresh=True), {"ok": True})

    def test_provider_fallback_returns_first_non_empty_frame(self) -> None:
        calls: list[str] = []

        def fail() -> pd.DataFrame:
            calls.append("fail")
            raise RuntimeError("offline")

        def empty() -> pd.DataFrame:
            calls.append("empty")
            return pd.DataFrame()

        def success() -> pd.DataFrame:
            calls.append("success")
            return pd.DataFrame({"code": ["300750"]})

        result = _first_success(
            [
                ("bad", fail),
                ("empty", empty),
                ("good", success),
            ]
        )

        self.assertEqual(result.provider, "good")
        self.assertEqual(result.row_count, 1)
        self.assertEqual(calls, ["fail", "empty", "success"])
        self.assertTrue(any("bad" in warning for warning in result.warnings))

    def test_first_success_records_actual_eastmoney_host(self) -> None:
        def success() -> pd.DataFrame:
            frame = pd.DataFrame({"f12": ["300750"], "f14": ["CATL"]})
            frame.attrs["eastmoney_host"] = "push2.eastmoney.com"
            return frame

        result = _first_success([("eastmoney_direct", success)])

        self.assertEqual(result.provider, "eastmoney_direct:push2.eastmoney.com")

    def test_eastmoney_clist_host_fallback_and_pagination(self) -> None:
        calls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: dict):
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self._payload

        def fake_get(url: str, **kwargs) -> FakeResponse:
            host = url.split("/")[2]
            page = str(kwargs["params"]["pn"])
            calls.append(f"{host}:{page}")
            if host == "bad.eastmoney.com":
                raise requests.Timeout("slow host")
            payloads = {
                "1": {
                    "rc": 0,
                    "data": {
                        "total": 3,
                        "diff": [
                            {"f12": "300750", "f14": "CATL", "f3": 1.0},
                            {"f12": "002371", "f14": "NAURA", "f3": 2.0},
                        ],
                    },
                },
                "2": {
                    "rc": 0,
                    "data": {
                        "total": 3,
                        "diff": [{"f12": "688981", "f14": "SMIC", "f3": -1.0}],
                    },
                },
            }
            return FakeResponse(payloads[page])

        with patch("research.data_sources.requests.get", side_effect=fake_get):
            frame = _fetch_eastmoney_clist(
                {
                    "pn": "1",
                    "pz": "2",
                    "fields": "f12,f14,f3",
                    "fs": "m:0 t:6",
                },
                hosts=("bad.eastmoney.com", "push2.eastmoney.com"),
            )

        self.assertEqual(frame.attrs["eastmoney_host"], "push2.eastmoney.com")
        self.assertEqual(frame.shape[0], 3)
        self.assertEqual(
            calls,
            [
                "bad.eastmoney.com:1",
                "push2.eastmoney.com:1",
                "push2.eastmoney.com:2",
            ],
        )

    def test_eastmoney_a_stock_direct_uses_clist_client(self) -> None:
        with patch("research.data_sources._fetch_eastmoney_clist") as fetch:
            fetch.return_value = pd.DataFrame({"f12": ["300750"], "f14": ["CATL"]})

            frame = fetch_eastmoney_a_stock_spot_direct()

        self.assertEqual(frame.iloc[0]["f12"], "300750")
        self.assertIn("m:0 t:6", fetch.call_args.args[0]["fs"])

    def test_filters_hard_exclude_st_and_bse(self) -> None:
        candidates = [
            Candidate(symbol="430001", name="Sample"),
            Candidate(symbol="300750", name="ST Sample"),
            Candidate(symbol="300751", name="Clean Sample"),
        ]

        active, excluded = apply_filters(candidates)

        self.assertEqual([item.symbol for item in active], ["300751"])
        self.assertEqual({item.symbol for item in excluded}, {"430001", "300750"})
        self.assertTrue(all("hard_exclusion" in ",".join(item.risk_flags) for item in excluded))

    def test_scoring_and_tool_wrapper_are_consistent(self) -> None:
        candidate = Candidate(
            symbol="300750",
            name="CATL",
            matched_keywords=["battery", "supply chain"],
            provenance=["name match", "concept board"],
            evidence=CandidateEvidence(
                evidence_tier=EvidenceTier.HARD,
                customer_or_order_summary="large order with major customer",
                estimated_exposure="30%+",
            ),
        )

        direct = score_candidate(candidate).to_dict()
        wrapped = tool_score_candidate(candidate)

        self.assertEqual(direct["symbol"], "300750")
        self.assertEqual(direct["total"], wrapped["total"])
        self.assertGreater(direct["total"], 50)

    def test_render_markdown_report_contains_required_sections(self) -> None:
        request = ResearchRequest(us_symbol="NVDA", keywords=["HBM"])
        candidate = Candidate(symbol="300308", name="Sample HBM", matched_keywords=["HBM"])
        etf = EtfCandidate(code="159995", name="Chip ETF", theme="HBM", management_fee="0.50%")
        report = ResearchReport(
            request=request,
            trigger_packet=build_trigger_packet(request),
            core_candidates=[candidate],
            etf_candidates=[etf],
            scores={candidate.symbol: score_candidate(candidate)},
        )

        markdown = render_markdown_report(report)

        self.assertIn("Core Stock Candidates", markdown)
        self.assertIn("ETF Implementation", markdown)
        self.assertIn("Trading Plans", markdown)

    def test_cli_no_live_data_writes_report(self) -> None:
        with TemporaryDirectory() as tmp:
            exit_code = cli_main(
                [
                    "run",
                    "--us",
                    "NVDA",
                    "--keywords",
                    "HBM,cooling",
                    "--no-live-data",
                    "--output-dir",
                    tmp,
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(list(Path(tmp).glob("*.md"))), 1)

    def test_pipeline_no_live_data_is_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            request = ResearchRequest(us_symbol="NVDA", keywords=["HBM"])
            report, path = run_research(request, use_live_data=False, output_dir=Path(tmp))

            self.assertTrue(path.exists())
            self.assertEqual(report.request.us_symbol, "NVDA")
            self.assertTrue(report.theme_tree)
            self.assertTrue(report.data_warnings)


if __name__ == "__main__":
    unittest.main()
