from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_artifacts import ArtifactReport, check_run_dir  # noqa: E402


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CheckArtifactsTests(unittest.TestCase):
    def test_check_run_dir_accepts_pipeline_manifest_without_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = ROOT
            run = Path(tmp) / "runs" / "2025-03-28" / "TARGET-SAMPLE-8697" / "research"
            evidence = [
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
                    "content": {"title": "Price", "summary": "Summary", "excerpt": None, "metrics": {}},
                    "evaluation": {
                        "directness": "high",
                        "freshness": "high",
                        "impact_level": "low",
                        "direction_hint": "neutral",
                        "related_topics": [],
                        "hypothesis_impact": "Price data.",
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
            health = {
                "schema_version": "health_snapshot_v1",
                "run_id": "PIPE-TEST",
                "run_at": "2026-07-04T12:00:00+09:00",
                "target_id": "TARGET-SAMPLE-8697",
                "overall_status": "ok",
                "summary": "ok",
                "stats": {"evidence_total": 1},
                "sections": [],
            }
            write_json(run / "evidence.json", evidence)
            write_json(run / "health.json", health)
            write_json(
                run / "pipeline_manifest.json",
                {
                    "schema_version": "research_pipeline_manifest_v1",
                    "run_id": "PIPE-TEST",
                    "run_at": "2026-07-04T12:00:00+09:00",
                    "target_id": "TARGET-SAMPLE-8697",
                    "date": "2025-03-28",
                    "bucket": "research",
                    "provider": "mock",
                    "model": "deterministic-baseline",
                    "agent_execution": "sequential",
                    "paths": {
                        "evidence": str(run / "evidence.json"),
                        "health": str(run / "health.json"),
                    },
                    "status": "ok",
                },
            )
            report = ArtifactReport()
            check_run_dir(report, run, root, strict=False)
            self.assertEqual([], report.errors)


if __name__ == "__main__":
    unittest.main()
