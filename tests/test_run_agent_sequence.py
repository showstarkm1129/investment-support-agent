from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_agent_sequence import parse_llm_payload, run_sequence, validate_research_plan  # noqa: E402


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class RunAgentSequenceTests(unittest.TestCase):
    def sample_evidence(self) -> list[dict]:
        return [
            {
                "schema_version": "evidence_v1",
                "evidence_id": "E20250328-001",
                "identity": {
                    "target_id": "TARGET-SAMPLE-8697",
                    "stock_code": "8697",
                    "company_name": "日本取引所グループ",
                    "collected_at": "2026-07-04T12:00:00+09:00",
                    "published_at": "2025-03-28T15:30:00+09:00",
                },
                "source": {
                    "source_type": "price_volume",
                    "source_name": "J-Quants API V2",
                    "source_url": None,
                    "source_reliability": "A",
                    "save_policy": "structured_data",
                },
                "content": {
                    "title": "J-Quants日次価格: 86970 2025-03-28",
                    "summary": "終値は始値を下回った。",
                    "excerpt": None,
                    "metrics": {"open": 110, "close": 100, "volume": 200},
                },
                "evaluation": {
                    "directness": "high",
                    "freshness": "high",
                    "impact_level": "low",
                    "direction_hint": "downside",
                    "related_topics": ["株価"],
                    "hypothesis_impact": "価格データ。",
                    "usable_for_market_readout": True,
                },
                "workflow": {
                    "human_review_status": "unread",
                    "human_note": "",
                    "used_in_decision": False,
                    "review_due_date": None,
                    "duplicate_of": None,
                    "related_evidence_ids": [],
                },
            }
        ]

    def args(self, evidence_path: Path, out_dir: Path) -> Namespace:
        return Namespace(
            evidence=evidence_path,
            out_dir=out_dir,
            target_id="TARGET-SAMPLE-8697",
            stock_code="8697",
            company_name="日本取引所グループ",
            report_date="2025-03-28",
            market="prime",
            theme=["取引所"],
            run_id="SEQ-TEST",
            provider="mock",
            model="deterministic-baseline",
            codex_reasoning_effort="low",
            codex_timeout=60,
            max_attempts=1,
            env_file=None,
            save_prompts=False,
            save_raw_responses=False,
            resume=False,
        )

    def test_validate_research_plan_requires_lists(self) -> None:
        plan = {
            "schema_version": "research_plan_v1",
            "agent_name": "search_design",
            "research_questions": [],
            "required_sources": [],
            "fetch_modules": [],
            "priority": [],
            "expected_evidence_types": [],
            "stop_conditions": [],
            "health_notes": [],
        }
        validate_research_plan(plan)

    def test_run_sequence_mock_writes_all_step_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            out_dir = root / "sequence"
            write_json(evidence_path, self.sample_evidence())
            manifest = run_sequence(self.args(evidence_path, out_dir))
            self.assertEqual("ok", manifest["status"])
            self.assertTrue((out_dir / "agent_steps" / "search_design.json").is_file())
            self.assertTrue((out_dir / "agent_steps" / "evidence_builder.json").is_file())
            evidence_builder = json.loads((out_dir / "agent_steps" / "evidence_builder.json").read_text(encoding="utf-8"))
            self.assertEqual(["E20250328-001"], evidence_builder["accepted_evidence_ids"])
            for agent in ["bull", "bear", "contradiction", "pricing"]:
                self.assertTrue((out_dir / "agent_steps" / f"{agent}.json").is_file())
            self.assertTrue((out_dir / "agent_steps" / "report_judge.json").is_file())
            self.assertTrue((out_dir / "agent_outputs.json").is_file())
            self.assertTrue((out_dir / "report_judge.json").is_file())
            self.assertTrue((out_dir / "agent_sequence_health.json").is_file())
            self.assertTrue((out_dir / "agent_sequence_status.json").is_file())
            status = json.loads((out_dir / "agent_sequence_status.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", status["status"])
            self.assertEqual(
                ["search_design", "evidence_builder", "bull", "bear", "contradiction", "pricing", "report_judge"],
                status["completed_steps"],
            )
            health = json.loads((out_dir / "health.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", health["overall_status"])

    def test_run_sequence_resume_reuses_valid_step_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            out_dir = root / "sequence"
            write_json(evidence_path, self.sample_evidence())
            args = self.args(evidence_path, out_dir)
            run_sequence(args)
            (out_dir / "agent_outputs.json").unlink()
            (out_dir / "report_judge.json").unlink()
            resumed_args = self.args(evidence_path, out_dir)
            resumed_args.resume = True
            with patch("run_agent_sequence.run_step", side_effect=AssertionError("should not call provider")):
                manifest = run_sequence(resumed_args)
            self.assertEqual("ok", manifest["status"])
            self.assertEqual(
                ["search_design", "evidence_builder", "bull", "bear", "contradiction", "pricing", "report_judge"],
                manifest["resumed_steps"],
            )
            self.assertTrue((out_dir / "agent_outputs.json").is_file())
            self.assertTrue((out_dir / "report_judge.json").is_file())
            health = json.loads((out_dir / "agent_sequence_health.json").read_text(encoding="utf-8"))
            checks = [item for section in health["sections"] for item in section["checks"]]
            self.assertTrue(any(item["check_id"] == "search_design" and item["status"] == "skipped" for item in checks))
            status = json.loads((out_dir / "agent_sequence_status.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", status["status"])
            self.assertEqual(
                ["search_design", "evidence_builder", "bull", "bear", "contradiction", "pricing", "report_judge"],
                status["resumed_steps"],
            )

    def test_run_sequence_error_status_marks_failed_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            out_dir = root / "sequence"
            write_json(evidence_path, self.sample_evidence())
            with patch("run_agent_sequence.run_step", side_effect=RuntimeError("provider down")):
                with self.assertRaises(RuntimeError):
                    run_sequence(self.args(evidence_path, out_dir))
            status = json.loads((out_dir / "agent_sequence_status.json").read_text(encoding="utf-8"))
            self.assertEqual("error", status["status"])
            self.assertEqual("search_design", status["failed_step"])
            self.assertEqual("error", status["steps"][0]["status"])


if __name__ == "__main__":
    unittest.main()
