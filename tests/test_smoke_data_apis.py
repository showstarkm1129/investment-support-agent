from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from smoke_data_apis import assert_no_secret_leak, sanitize_url, summarize_edinet_payload, summarize_jquants_payload


class SmokeDataApiTests(unittest.TestCase):
    def test_sanitize_url_redacts_secret_values(self) -> None:
        url = "https://example.test/path?Subscription-Key=secret-value&x=1"
        self.assertEqual(
            "https://example.test/path?Subscription-Key=REDACTED&x=1",
            sanitize_url(url, ["secret-value"]),
        )

    def test_assert_no_secret_leak_raises_on_saved_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.json"
            path.write_text(json.dumps({"url": "secret-value"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                assert_no_secret_leak(path, ["secret-value"])

    def test_summarize_jquants_payload_supports_v2_bars(self) -> None:
        summary = summarize_jquants_payload({"bars": [{"code": "86970", "date": "20250328"}]})
        self.assertEqual(1, summary["row_count"])
        self.assertEqual(["code", "date"], summary["first_row_keys"])

    def test_summarize_edinet_payload_counts_results(self) -> None:
        summary = summarize_edinet_payload({"metadata": {"status": "200"}, "results": [{"docID": "S1"}]})
        self.assertEqual(1, summary["result_count"])
        self.assertEqual(["docID"], summary["first_result_keys"])


if __name__ == "__main__":
    unittest.main()
