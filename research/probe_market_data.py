"""Smoke-test market data interfaces for the US-to-A-share research project."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys

import akshare as ak
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.data_sources import fetch_a_stock_spot, fetch_etf_spot


Probe = tuple[str, Callable[[], pd.DataFrame]]


def print_probe(name: str, fetch: Callable[[], pd.DataFrame]) -> None:
    print(f"\n## {name}")
    try:
        frame = fetch()
    except Exception as exc:  # noqa: BLE001 - probe should report all failures
        print(f"FAIL {type(exc).__name__}: {exc}")
        return

    print(f"OK shape={frame.shape}")
    print(frame.head(5).to_string(index=False))


def main() -> None:
    print(f"akshare={ak.__version__}")
    for name, fetch in [
        ("a_stock_spot_provider", fetch_a_stock_spot),
        ("etf_spot_provider", fetch_etf_spot),
    ]:
        print(f"\n## {name}")
        try:
            result = fetch(use_cache=False)
        except Exception as exc:  # noqa: BLE001 - probe should report all failures
            print(f"FAIL {type(exc).__name__}: {exc}")
        else:
            print(f"provider={result.provider} shape={result.data.shape}")
            print(result.data.head(5).to_string(index=False))

    probes: list[Probe] = [
        ("stock_zh_a_spot_sina", lambda: ak.stock_zh_a_spot()),
        (
            "stock_zh_a_daily_sina",
            lambda: ak.stock_zh_a_daily(
                symbol="sz000001",
                start_date="20260101",
                end_date="20260617",
                adjust="qfq",
            ),
        ),
        (
            "stock_zh_a_hist_tx",
            lambda: ak.stock_zh_a_hist_tx(
                symbol="sz000001",
                start_date="20260101",
                end_date="20260617",
                adjust="qfq",
            ),
        ),
        ("fund_etf_spot_ths", lambda: ak.fund_etf_spot_ths()),
        ("fund_etf_hist_sina", lambda: ak.fund_etf_hist_sina(symbol="sh510300")),
    ]

    for name, fetch in probes:
        print_probe(name, fetch)


if __name__ == "__main__":
    main()
