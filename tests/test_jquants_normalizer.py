from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

from normalize_daily_quotes import normalize_raw, normalize_row, output_path  # noqa: E402


class JQuantsNormalizerTests(unittest.TestCase):
    def test_normalize_row_maps_jquants_fields(self) -> None:
        row = {
            "Date": "2025-03-28",
            "Code": "86970",
            "O": 100.0,
            "H": 110.0,
            "L": 90.0,
            "C": 105.0,
            "Vo": 12345,
            "Va": 67890,
            "AdjFactor": 1.0,
        }
        normalized = normalize_row(row)
        self.assertEqual("2025-03-28", normalized["date"])
        self.assertEqual("86970", normalized["code"])
        self.assertEqual(105.0, normalized["close"])
        self.assertEqual(12345, normalized["volume"])
        self.assertEqual(67890, normalized["turnover_value"])
        self.assertEqual(1.0, normalized["adjustment_factor"])

    def test_normalize_raw_creates_connector_artifact(self) -> None:
        raw = {
            "schema_version": "jquants_raw_daily_quotes_v1",
            "target_id": "TARGET-SAMPLE-8697",
            "code": "86970",
            "date": "2025-03-28",
            "status_code": 200,
            "summary": {"row_count": 1},
            "response": {"data": [{"Date": "2025-03-28", "Code": "86970", "C": 105.0}]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            normalized = normalize_raw(raw, raw_path=Path(tmp) / "raw.json")
        self.assertEqual("jquants_normalized_daily_quotes_v1", normalized["schema_version"])
        self.assertEqual(1, normalized["record_count"])
        self.assertTrue(normalized["quality"]["has_records"])
        self.assertEqual(105.0, normalized["records"][0]["close"])

    def test_normalize_raw_rejects_error_artifact(self) -> None:
        with self.assertRaises(ValueError):
            normalize_raw({"schema_version": "jquants_raw_daily_quotes_error_v1"}, raw_path=Path("error.json"))

    def test_output_path_uses_normalized_layout(self) -> None:
        self.assertEqual(
            Path("data/normalized/jquants/2025-03-28/TARGET-SAMPLE-8697.json"),
            output_path(out_root=Path("data/normalized/jquants"), target_id="TARGET-SAMPLE-8697", date="2025-03-28"),
        )


if __name__ == "__main__":
    unittest.main()
