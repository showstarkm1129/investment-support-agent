from __future__ import annotations

import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

from build_evidence import direction_hint, evidence_from_normalized, metrics_from_record  # noqa: E402


class JQuantsBuildEvidenceTests(unittest.TestCase):
    def test_direction_hint_from_open_close(self) -> None:
        self.assertEqual("upside", direction_hint({"open": 100, "close": 101}))
        self.assertEqual("downside", direction_hint({"open": 100, "close": 99}))
        self.assertEqual("neutral", direction_hint({"open": 100, "close": 100}))

    def test_metrics_from_record_keeps_expected_fields(self) -> None:
        metrics = metrics_from_record({"close": 100, "volume": 200, "unused": 300})
        self.assertEqual({"close": 100, "volume": 200}, metrics)

    def test_evidence_from_normalized_creates_schema_shaped_item(self) -> None:
        normalized = {
            "schema_version": "jquants_normalized_daily_quotes_v1",
            "target_id": "TARGET-SAMPLE-8697",
            "code": "86970",
            "date": "2025-03-28",
            "records": [{"date": "2025-03-28", "code": "86970", "open": 100, "close": 101, "volume": 200}],
        }
        evidence = evidence_from_normalized(
            normalized,
            stock_code="8697",
            company_name="日本取引所グループ",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("evidence_v1", item["schema_version"])
        self.assertEqual("E20250328-001", item["evidence_id"])
        self.assertEqual("TARGET-SAMPLE-8697", item["identity"]["target_id"])
        self.assertEqual("J-Quants API V2", item["source"]["source_name"])
        self.assertEqual("upside", item["evaluation"]["direction_hint"])

    def test_evidence_from_normalized_rejects_wrong_schema(self) -> None:
        with self.assertRaises(ValueError):
            evidence_from_normalized({}, stock_code="8697", company_name="日本取引所グループ")


if __name__ == "__main__":
    unittest.main()
