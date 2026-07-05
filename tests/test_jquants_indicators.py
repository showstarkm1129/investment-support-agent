from __future__ import annotations

import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

from build_indicators import direction_hint, evidence_from_indicators, indicator_metrics, indicators_from_normalized  # noqa: E402


class JQuantsIndicatorTests(unittest.TestCase):
    def records(self) -> list[dict]:
        return [
            {"date": f"2025-03-{day:02d}", "code": "86970", "open": 100 + day, "high": 105 + day, "low": 95 + day, "close": 100 + day, "volume": 1000 + day * 10}
            for day in range(24, 29)
        ]

    def normalized(self) -> dict:
        return {
            "schema_version": "jquants_normalized_daily_quotes_v1",
            "target_id": "TARGET-SAMPLE-8697",
            "code": "86970",
            "date": "2025-03-28",
            "records": self.records(),
            "source_raw_path": "raw.json",
        }

    def test_indicator_metrics_calculates_moving_average_and_volume_ratio(self) -> None:
        metrics = indicator_metrics(self.records())
        self.assertEqual("2025-03-28", metrics["date"])
        self.assertIsNotNone(metrics["ma_5"])
        self.assertIsNotNone(metrics["volume_ratio_5d"])
        self.assertIn("close_to_open_pct", metrics)

    def test_direction_hint_uses_change_metrics(self) -> None:
        self.assertEqual("upside", direction_hint({"change_pct": 1.0}))
        self.assertEqual("downside", direction_hint({"close_to_open_pct": -1.0}))
        self.assertEqual("neutral", direction_hint({}))

    def test_indicators_from_normalized_creates_artifact(self) -> None:
        indicators = indicators_from_normalized(self.normalized())
        self.assertEqual("jquants_derived_indicators_v1", indicators["schema_version"])
        self.assertTrue(indicators["quality"]["has_ma_5"])
        self.assertEqual(5, indicators["record_count"])

    def test_evidence_from_indicators_creates_evidence(self) -> None:
        indicators = indicators_from_normalized(self.normalized())
        evidence = evidence_from_indicators(
            indicators,
            stock_code="8697",
            company_name="日本取引所グループ",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        self.assertEqual("E20250328-051", evidence[0]["evidence_id"])
        self.assertEqual("J-Quants derived indicators", evidence[0]["source"]["source_name"])
        self.assertIn("ma_5", evidence[0]["content"]["metrics"])


if __name__ == "__main__":
    unittest.main()
