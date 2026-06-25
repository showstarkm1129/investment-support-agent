from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_agent_context import CONTRACTS, FLOW_AGENT_ORDER, FLOW_CHOICES, FLOW_TO_BUCKET, FLOW_TO_DOC


class FlowIntegrityTests(unittest.TestCase):
    def test_flow_docs_have_required_sections(self) -> None:
        for flow in FLOW_CHOICES:
            with self.subTest(flow=flow):
                text = (ROOT / FLOW_TO_DOC[flow]).read_text(encoding="utf-8")
                self.assertIn("## Inputs", text)
                self.assertIn("## Order", text)
                self.assertIn("## Outputs", text)

    def test_flow_mappings_point_to_existing_files(self) -> None:
        for flow in FLOW_CHOICES:
            with self.subTest(flow=flow):
                self.assertIn(flow, FLOW_TO_BUCKET)
                self.assertTrue((ROOT / FLOW_TO_DOC[flow]).is_file())
                self.assertTrue(FLOW_AGENT_ORDER[flow])

        for rel in CONTRACTS.values():
            with self.subTest(contract=rel):
                self.assertTrue((ROOT / rel).exists())

    def test_run_flow_prepares_manifest_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_flow.py"),
                    "--flow",
                    "morning_report",
                    "--target-id",
                    "TARGET-SAMPLE-6501",
                    "--date",
                    "2026-06-22",
                    "--runs-dir",
                    tmp,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            run_dir = Path(tmp) / "2026-06-22" / "TARGET-SAMPLE-6501" / "morning"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
            self.assertEqual("prepared", manifest["status"])
            self.assertEqual("morning_report", context["flow"])
            self.assertEqual("TARGET-SAMPLE-6501", context["target_id"])
            self.assertIn("evidence", context["outputs"])

    def test_run_flow_script_generates_agent_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_flow.py"),
                    "--script",
                    "semiconductor_sector_morning",
                    "--date",
                    "2026-06-25",
                    "--runs-dir",
                    tmp,
                    "--mode",
                    "simulate",
                    "--model",
                    "gpt-5-codex",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            run_dir = Path(tmp) / "2026-06-25" / "SECTOR-SEMICONDUCTOR" / "morning"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dir / "agent_trace.json").read_text(encoding="utf-8"))
            self.assertEqual("semiconductor_sector_morning", manifest["script"]["script_id"])
            self.assertEqual("gpt-5-codex", manifest["model"])
            self.assertEqual("SECTOR-SEMICONDUCTOR", context["target_id"])
            self.assertEqual(12, len(trace["steps"]))
            self.assertEqual("gpt-5-codex", trace["model"])
            self.assertIn("--model gpt-5-codex", trace["steps"][0]["suggested_command"])
            self.assertTrue((run_dir / "prompts" / "01_search_design.md").is_file())
            self.assertTrue((run_dir / "agent_outputs.json").is_file())


if __name__ == "__main__":
    unittest.main()
