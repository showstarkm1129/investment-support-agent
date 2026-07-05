from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from show_run_status import build_status_lines, resolve_run_dir  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ShowRunStatusTests(unittest.TestCase):
    def test_build_status_lines_summarizes_pipeline_and_agent_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "2025-03-28" / "TARGET-SAMPLE-8697" / "morning"
            write_json(
                run_dir / "pipeline_manifest.json",
                {
                    "schema_version": "research_pipeline_manifest_v1",
                    "run_id": "PIPE-TEST",
                    "provider": "codex_cli",
                    "model": "gpt-5.4-mini",
                    "status": "error",
                },
            )
            write_json(
                run_dir / "health.json",
                {
                    "schema_version": "health_snapshot_v1",
                    "stats": {"evidence_total": 3, "agent_success": 0, "agent_failed": 1, "report_outputs": 0},
                },
            )
            write_json(
                run_dir / "agent_sequence_manifest.json",
                {"schema_version": "agent_sequence_manifest_v1", "resumed_steps": ["search_design"]},
            )
            write_json(
                run_dir / "agent_sequence_status.json",
                {
                    "schema_version": "agent_sequence_status_v1",
                    "status": "error",
                    "current_step": None,
                    "failed_step": "bear",
                    "steps": [
                        {"agent_name": "search_design", "status": "resumed"},
                        {"agent_name": "evidence_builder", "status": "ok"},
                        {"agent_name": "bear", "status": "error"},
                    ],
                },
            )
            lines = build_status_lines(run_dir)
            text = "\n".join(lines)
            self.assertIn("pipeline_status: error", text)
            self.assertIn("agent_sequence_status: error", text)
            self.assertIn("failed_step: bear", text)
            self.assertIn("resumed_steps: 1", text)
            self.assertIn("search_design:resumed", text)

    def test_resolve_run_dir_accepts_manifest_path(self) -> None:
        path = resolve_run_dir(run_dir=None, manifest=Path("/tmp/example/pipeline_manifest.json"))
        self.assertEqual(Path("/tmp/example"), path)


if __name__ == "__main__":
    unittest.main()
