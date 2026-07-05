from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

from build_history import build_history, unique_records  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class JQuantsHistoryTests(unittest.TestCase):
    def raw(self, date: str, close: float) -> dict:
        return {
            "schema_version": "jquants_raw_daily_quotes_v1",
            "target_id": "TARGET-SAMPLE-8697",
            "code": "86970",
            "date": date,
            "status_code": 200,
            "summary": {"row_count": 1},
            "response": {
                "data": [
                    {
                        "Date": date,
                        "Code": "86970",
                        "O": close - 1,
                        "H": close + 2,
                        "L": close - 3,
                        "C": close,
                        "Vo": 1000,
                    }
                ]
            },
        }

    def test_unique_records_deduplicates_by_date_and_code(self) -> None:
        records = [
            {"date": "2025-03-28", "code": "86970", "close": 1},
            {"date": "2025-03-27", "code": "86970", "close": 2},
            {"date": "2025-03-28", "code": "86970", "close": 3},
        ]
        unique = unique_records(records)
        self.assertEqual(["2025-03-27", "2025-03-28"], [item["date"] for item in unique])
        self.assertEqual(3, unique[-1]["close"])

    def test_build_history_combines_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index, date in enumerate(["2025-03-26", "2025-03-27", "2025-03-28"], start=1):
                path = Path(tmp) / f"{date}.json"
                write_json(path, self.raw(date, 100 + index))
                paths.append(path)
            history = build_history(paths)
        self.assertEqual("jquants_normalized_daily_quotes_v1", history["schema_version"])
        self.assertEqual(3, history["record_count"])
        self.assertEqual("2025-03-28", history["date"])
        self.assertEqual(3, history["quality"]["source_file_count"])


if __name__ == "__main__":
    unittest.main()
