from __future__ import annotations

import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

from build_relative_comparison import evidence_from_relative_comparison, relative_comparison_from_normalized  # noqa: E402


class JQuantsRelativeComparisonTests(unittest.TestCase):
    def normalized(self, *, target_id: str, code: str, close_base: float, volume_base: float = 1000.0) -> dict:
        records = []
        for index, day in enumerate(range(24, 29), start=1):
            close = close_base + index * 10
            records.append(
                {
                    "date": f"2025-03-{day:02d}",
                    "code": code,
                    "open": close - 2,
                    "high": close + 5,
                    "low": close - 8,
                    "close": close,
                    "volume": volume_base + index * 100,
                }
            )
        return {
            "schema_version": "jquants_normalized_daily_quotes_v1",
            "provider": "jquants",
            "target_id": target_id,
            "code": code,
            "date": "2025-03-28",
            "source_raw_path": "raw.json",
            "record_count": len(records),
            "records": records,
        }

    def test_relative_comparison_calculates_benchmark_spread(self) -> None:
        target = self.normalized(target_id="TARGET-SAMPLE-8697", code="86970", close_base=1500)
        benchmark = self.normalized(target_id="BENCH-SECTOR", code="13060", close_base=3000)
        comparison = relative_comparison_from_normalized(
            target_normalized=target,
            benchmarks=[{"label": "SectorETF", "normalized": benchmark}],
        )
        self.assertEqual("jquants_relative_comparison_v1", comparison["schema_version"])
        self.assertEqual(1, comparison["quality"]["benchmark_count"])
        self.assertEqual(1, comparison["quality"]["comparable_count"])
        self.assertEqual("SectorETF", comparison["comparisons"][0]["label"])
        self.assertIn("relative_pct", comparison["comparisons"][0])

    def test_evidence_from_relative_comparison_creates_market_supply_evidence(self) -> None:
        target = self.normalized(target_id="TARGET-SAMPLE-8697", code="86970", close_base=1500)
        benchmark = self.normalized(target_id="BENCH-SECTOR", code="13060", close_base=3000)
        comparison = relative_comparison_from_normalized(
            target_normalized=target,
            benchmarks=[{"label": "SectorETF", "normalized": benchmark}],
        )
        evidence = evidence_from_relative_comparison(
            comparison,
            stock_code="8697",
            company_name="日本取引所グループ",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("E20250328-061", item["evidence_id"])
        self.assertEqual("market_supply", item["source"]["source_type"])
        self.assertEqual("J-Quants relative benchmark comparison", item["source"]["source_name"])
        self.assertIn("SectorETF_relative_pct", item["content"]["metrics"])


if __name__ == "__main__":
    unittest.main()
