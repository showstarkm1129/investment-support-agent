from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_agent_context import CONTRACTS, FLOW_AGENT_ORDER, FLOW_CHOICES, FLOW_TO_BUCKET, FLOW_TO_DOC
from run_flow import load_env_file, parse_env_line


class FlowIntegrityTests(unittest.TestCase):
    def test_env_file_loader_does_not_expose_secret_values_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env.local"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=sk-test-secret-value",
                        "ANTHROPIC_API_KEY='anthropic-secret'",
                        "JQUANTS_API_KEY=jquants-secret",
                        "COMMENTED=value # comment is ignored",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_flow.py"),
                    "--script",
                    "search_design_smoke",
                    "--date",
                    "2026-06-25",
                    "--runs-dir",
                    str(tmp_path / "runs"),
                    "--mode",
                    "dry-run",
                    "--env-file",
                    str(env_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest_path = tmp_path / "runs" / "2026-06-25" / "SMOKE-SEARCH-DESIGN" / "morning" / "manifest.json"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)

            self.assertTrue(manifest["secrets"]["values_exposed"] is False)
            self.assertIn("OPENAI_API_KEY", manifest["secrets"]["loaded_env_keys"])
            self.assertIn("ANTHROPIC_API_KEY", manifest["secrets"]["loaded_env_keys"])
            self.assertIn("JQUANTS_API_KEY", manifest["secrets"]["loaded_env_keys"])
            self.assertNotIn("sk-test-secret-value", manifest_text)
            self.assertNotIn("anthropic-secret", manifest_text)
            self.assertNotIn("jquants-secret", manifest_text)

    def test_parse_env_line_handles_quotes_and_comments(self) -> None:
        self.assertEqual(("OPENAI_API_KEY", "sk-abc"), parse_env_line("OPENAI_API_KEY=sk-abc"))
        self.assertEqual(("NEWS_API_KEY", "quoted#value"), parse_env_line('export NEWS_API_KEY="quoted#value" # trailing'))
        self.assertIsNone(parse_env_line("# OPENAI_API_KEY=ignored"))

    def test_load_env_file_does_not_override_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("OPENAI_API_KEY=file-value\nGEMINI_API_KEY=file-gemini\n", encoding="utf-8")
            old_openai = None
            had_openai = "OPENAI_API_KEY" in os.environ
            if had_openai:
                old_openai = os.environ["OPENAI_API_KEY"]
            os.environ["OPENAI_API_KEY"] = "existing-value"
            try:
                loaded = load_env_file(env_path)
                self.assertNotIn("OPENAI_API_KEY", loaded)
                self.assertIn("GEMINI_API_KEY", loaded)
                self.assertEqual("existing-value", os.environ["OPENAI_API_KEY"])
            finally:
                if had_openai and old_openai is not None:
                    os.environ["OPENAI_API_KEY"] = old_openai
                else:
                    os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("GEMINI_API_KEY", None)

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

    def test_search_design_smoke_tracks_expected_script_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_flow.py"),
                    "--script",
                    "search_design_smoke",
                    "--date",
                    "2026-06-25",
                    "--runs-dir",
                    tmp,
                    "--mode",
                    "dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            run_dir = Path(tmp) / "2026-06-25" / "SMOKE-SEARCH-DESIGN" / "morning"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dir / "agent_trace.json").read_text(encoding="utf-8"))
            prompt = (run_dir / "prompts" / "01_search_design.md").read_text(encoding="utf-8")
            expected_outputs = manifest["expected_script_outputs"]

            self.assertEqual(
                str(run_dir / "search_plan.json"),
                expected_outputs["search_design_search_plan.json"],
            )
            self.assertNotIn("script_output_search_design_search_plan.json", manifest["paths"])
            self.assertEqual([str(run_dir / "search_plan.json")], trace["steps"][0]["expected_outputs"])
            self.assertIn("Write These Files", prompt)
            self.assertIn("stop immediately", prompt)

    def test_two_agent_smoke_uses_canonical_evidence_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_flow.py"),
                    "--script",
                    "search_to_evidence_smoke",
                    "--date",
                    "2026-06-25",
                    "--runs-dir",
                    tmp,
                    "--mode",
                    "dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            run_dir = Path(tmp) / "2026-06-25" / "SMOKE-6501" / "morning"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            context = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dir / "agent_trace.json").read_text(encoding="utf-8"))

            self.assertEqual(str(run_dir / "evidence.json"), context["outputs"]["evidence"])
            self.assertEqual(str(run_dir / "evidence.json"), manifest["expected_script_outputs"]["evidence"])
            self.assertEqual(2, len(trace["steps"]))
            self.assertEqual("search_design", trace["steps"][0]["agent_id"])
            self.assertEqual("evidence_builder", trace["steps"][1]["agent_id"])
            self.assertEqual([str(run_dir / "search_plan.json")], trace["steps"][0]["expected_outputs"])
            self.assertEqual([str(run_dir / "evidence.json")], trace["steps"][1]["expected_outputs"])


if __name__ == "__main__":
    unittest.main()
