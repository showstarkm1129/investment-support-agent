from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


edinet_build = load_module("edinet_build_evidence", ROOT / "connectors" / "edinet" / "build_evidence.py")
edinet_fetch = load_module("edinet_fetch_documents", ROOT / "connectors" / "edinet" / "fetch_documents.py")

document_datetime = edinet_build.document_datetime
evidence_from_raw = edinet_build.evidence_from_raw
matches_target = edinet_build.matches_target
raw_artifact = edinet_fetch.raw_artifact
sanitize_url = edinet_fetch.sanitize_url
summarize_payload = edinet_fetch.summarize_payload


class EdinetConnectorTests(unittest.TestCase):
    def sample_payload(self) -> dict:
        return {
            "metadata": {"status": "200"},
            "results": [
                {
                    "docID": "S100TEST",
                    "edinetCode": "E03814",
                    "secCode": "86970",
                    "filerName": "日本取引所グループ",
                    "docDescription": "臨時報告書",
                    "submitDateTime": "2025-03-28 15:00",
                    "docTypeCode": "120",
                    "formCode": "030000",
                    "ordinanceCode": "010",
                }
            ],
        }

    def test_sanitize_url_redacts_subscription_key(self) -> None:
        url = "https://example.test?Subscription-Key=secret-value"
        self.assertNotIn("secret-value", sanitize_url(url, ["secret-value"]))

    def test_summarize_payload_counts_results(self) -> None:
        summary = summarize_payload(self.sample_payload())
        self.assertEqual(1, summary["result_count"])
        self.assertIn("docID", summary["first_result_keys"])

    def test_matches_target_by_sec_code_or_filer_name(self) -> None:
        row = self.sample_payload()["results"][0]
        self.assertTrue(matches_target(row, sec_code="8697", filer_name_contains=None))
        self.assertTrue(matches_target(row, sec_code=None, filer_name_contains="取引所"))
        self.assertFalse(matches_target(row, sec_code="6501", filer_name_contains=None))

    def test_document_datetime_to_iso_jst(self) -> None:
        self.assertEqual("2025-03-28T15:00:00+09:00", document_datetime({"submitDateTime": "2025-03-28 15:00"}, "2025-03-28"))

    def test_evidence_from_raw_creates_edinet_evidence(self) -> None:
        raw = raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            date="2025-03-28",
            doc_type="2",
            status_code=200,
            request_url="https://example.test/documents.json?Subscription-Key=REDACTED",
            payload=self.sample_payload(),
        )
        evidence = evidence_from_raw(
            raw,
            stock_code="8697",
            company_name="日本取引所グループ",
            sec_code="8697",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("E20250328-101", item["evidence_id"])
        self.assertEqual("disclosure_edinet", item["source"]["source_type"])
        self.assertEqual("neutral", item["evaluation"]["direction_hint"])

    def test_evidence_from_raw_records_no_matching_disclosure(self) -> None:
        raw = raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            date="2025-03-28",
            doc_type="2",
            status_code=200,
            request_url="https://example.test/documents.json?Subscription-Key=REDACTED",
            payload={"metadata": {"status": "200"}, "results": []},
        )
        evidence = evidence_from_raw(
            raw,
            stock_code="8697",
            company_name="日本取引所グループ",
            sec_code="8697",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("E20250328-101", item["evidence_id"])
        self.assertEqual("disclosure_edinet", item["source"]["source_type"])
        self.assertEqual(0, item["content"]["metrics"]["matched_document_count"])


if __name__ == "__main__":
    unittest.main()
