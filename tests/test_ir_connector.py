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


ir_fetch = load_module("ir_fetch_page", ROOT / "connectors" / "ir" / "fetch_page.py")
ir_build = load_module("ir_build_evidence", ROOT / "connectors" / "ir" / "build_evidence.py")


class IrConnectorTests(unittest.TestCase):
    def test_parse_metadata_extracts_title_description_and_snippet(self) -> None:
        html = """
        <html><head><title>IR Library</title><meta name="description" content="Official IR page"></head>
        <body><script>ignore()</script><h1>Investor Relations</h1><p>Short snippet text.</p></body></html>
        """
        metadata = ir_fetch.parse_metadata(html)
        self.assertEqual("IR Library", metadata["title"])
        self.assertEqual("Official IR page", metadata["description"])
        self.assertIn("Investor Relations", metadata["snippet"])

    def test_raw_artifact_has_expected_shape(self) -> None:
        artifact = ir_fetch.raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            company_name="日本取引所グループ",
            url="https://example.com/ir",
            status_code=200,
            content_type="text/html",
            metadata={"title": "IR", "description": "desc", "snippet": "snippet"},
        )
        self.assertEqual("ir_raw_page_v1", artifact["schema_version"])
        self.assertTrue(artifact["summary"]["has_title"])

    def test_evidence_from_raw_creates_ir_evidence(self) -> None:
        raw = ir_fetch.raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            company_name="日本取引所グループ",
            url="https://example.com/ir",
            status_code=200,
            content_type="text/html",
            metadata={"title": "IR", "description": "desc", "snippet": "snippet"},
        )
        evidence = ir_build.evidence_from_raw(
            raw,
            stock_code="8697",
            company_name="日本取引所グループ",
            date="2025-03-28",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("E20250328-301", item["evidence_id"])
        self.assertEqual("ir", item["source"]["source_type"])
        self.assertEqual("A", item["source"]["source_reliability"])


if __name__ == "__main__":
    unittest.main()
