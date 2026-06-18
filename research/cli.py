"""Command-line interface for the research layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import get_default_settings
from .pipeline import run_research
from .schemas import ResearchRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="US-triggered A-share research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a research report")
    run_parser.add_argument("--us", required=False, default="NVDA")
    run_parser.add_argument("--keywords", default="")
    run_parser.add_argument("--input", type=Path)
    run_parser.add_argument("--output-dir", type=Path)
    run_parser.add_argument("--no-agent", action="store_true")
    run_parser.add_argument("--no-live-data", action="store_true")

    subparsers.add_parser("show-config", help="print default settings")
    subparsers.add_parser("probe", help="run market data probe")

    args = parser.parse_args(argv)
    if args.command == "show-config":
        print(json.dumps(get_default_settings().score_weights.__dict__, indent=2))
        print(json.dumps(_settings_summary(), indent=2, default=str))
        return 0
    if args.command == "probe":
        from .probe_market_data import main as probe_main

        probe_main()
        return 0
    if args.command == "run":
        request = _request_from_args(args)
        _report, path = run_research(
            request,
            use_live_data=not args.no_live_data,
            output_dir=args.output_dir,
        )
        print(path)
        return 0
    return 1


def _request_from_args(args: argparse.Namespace) -> ResearchRequest:
    raw_context = ""
    if args.input:
        raw_context = args.input.read_text(encoding="utf-8")
    keywords = [item.strip() for item in args.keywords.split(",") if item.strip()]
    if not keywords and raw_context:
        keywords = _keywords_from_context(raw_context)
    return ResearchRequest(
        us_symbol=args.us.upper(),
        keywords=keywords,
        raw_context=raw_context,
    )


def _keywords_from_context(text: str) -> list[str]:
    separators = [",", "，", "\n", ";", "；"]
    normalized = text
    for sep in separators[1:]:
        normalized = normalized.replace(sep, separators[0])
    return [item.strip() for item in normalized.split(",") if item.strip()][:20]


def _settings_summary() -> dict[str, object]:
    settings = get_default_settings()
    return {
        "market_scope": settings.market_scope,
        "hard_excluded_boards": settings.hard_excluded_boards,
        "core_candidate_target": settings.core_candidate_target,
        "max_core_candidates": settings.max_core_candidates,
        "default_rsi_overheated": settings.default_rsi_overheated,
        "report_dir": str(settings.report_dir),
        "cache_dir": str(settings.cache.cache_dir),
    }


if __name__ == "__main__":
    raise SystemExit(main())
