from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connectors" / "jquants"))

import fetch_daily_quotes  # noqa: E402
from fetch_daily_quotes import (  # noqa: E402
    assert_no_secret_leak,
    display_date,
    fetch_and_save,
    output_path,
    raw_artifact,
    rows_from_payload,
    sanitize_url,
    summarize_payload,
)


class JQuantsConnectorTests(unittest.TestCase):
    def test_display_date_accepts_compact_and_hyphenated(self) -> None:
        self.assertEqual("2025-03-28", display_date("20250328"))
        self.assertEqual("2025-03-28", display_date("2025-03-28"))

    def test_output_path_uses_expected_raw_layout(self) -> None:
        path = output_path(
            out_root=Path("data/raw/jquants"),
            target_id="TARGET-SAMPLE-8697",
            date="2025-03-28",
            code="86970",
        )
        self.assertEqual(
            Path("data/raw/jquants/2025-03-28/TARGET-SAMPLE-8697/daily_quotes_86970_20250328_raw.json"),
            path,
        )

    def test_summarize_payload_handles_v2_data_key(self) -> None:
        payload = {"data": [{"Date": "2025-03-28", "Code": "86970", "C": 100.0}]}
        self.assertEqual(1, len(rows_from_payload(payload)))
        summary = summarize_payload(payload)
        self.assertEqual(1, summary["row_count"])
        self.assertEqual(["C", "Code", "Date"], summary["first_row_keys"])

    def test_raw_artifact_does_not_store_secret_in_url(self) -> None:
        api_key = "secret-key"
        url = sanitize_url("https://example.test/path?key=secret-key", [api_key])
        artifact = raw_artifact(
            target_id="TARGET",
            code="86970",
            date="20250328",
            status_code=200,
            request_url=url,
            payload={"data": []},
        )
        text = json.dumps(artifact)
        self.assertNotIn(api_key, text)
        self.assertIn("REDACTED", text)

    def test_assert_no_secret_leak_detects_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw.json"
            path.write_text('{"key": "secret-key"}', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                assert_no_secret_leak(path, ["secret-key"])

    def test_fetch_and_save_writes_error_artifact_without_secret(self) -> None:
        original_request_json = fetch_daily_quotes.request_json

        def fake_request_json(**_: object) -> tuple[int, dict[str, object]]:
            raise urllib.error.URLError("network down")

        fetch_daily_quotes.request_json = fake_request_json
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError):
                    fetch_and_save(
                        api_key="secret-key",
                        target_id="TARGET",
                        code="86970",
                        date="2025-03-28",
                        out_root=Path(tmp),
                        timeout=1,
                    )
                files = list(Path(tmp).glob("2025-03-28/TARGET/*_error.json"))
                self.assertEqual(1, len(files))
                text = files[0].read_text(encoding="utf-8")
                payload = json.loads(text)
                self.assertEqual("jquants_raw_daily_quotes_error_v1", payload["schema_version"])
                self.assertIn("network down", payload["error"])
                self.assertNotIn("secret-key", text)
        finally:
            fetch_daily_quotes.request_json = original_request_json


if __name__ == "__main__":
    unittest.main()
