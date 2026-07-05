from __future__ import annotations

import json
import unittest
from pathlib import Path

import sys

try:
    from jsonschema import Draft202012Validator as JsonSchemaValidator
except ImportError:
    from jsonschema import Draft7Validator as JsonSchemaValidator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_agent_team_readout import build_outputs, weight_from_counts  # noqa: E402


def json_load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


class BuildAgentTeamReadoutTests(unittest.TestCase):
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
                    "summary": "終値は始値を上回った。",
                    "excerpt": None,
                    "metrics": {"open": 100, "close": 110, "volume": 200},
                },
                "evaluation": {
                    "directness": "high",
                    "freshness": "high",
                    "impact_level": "low",
                    "direction_hint": "upside",
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

    def test_weight_from_counts_sums_to_100(self) -> None:
        weights = weight_from_counts({"upside": 1, "downside": 1, "contradiction": 0, "priced_in": 0}, True)
        self.assertEqual(100, sum(weights.values()))
        self.assertGreater(weights["upside"], 0)
        self.assertGreater(weights["downside"], 0)

    def test_build_outputs_creates_four_agents_and_judge(self) -> None:
        agents, judge = build_outputs(
            self.sample_evidence(),
            target_id="TARGET-SAMPLE-8697",
            stock_code="8697",
            company_name="日本取引所グループ",
            market="prime",
            themes=["取引所"],
            report_date="2025-03-28",
            run_id="ATR-TEST",
            run_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual("agent_outputs_bundle_v1", agents["schema_version"])
        self.assertEqual(["bull", "bear", "contradiction", "pricing"], [item["agent_name"] for item in agents["agent_outputs"]])
        self.assertEqual(["E20250328-001"], agents["agent_outputs"][0]["evidence_ids"])
        self.assertEqual("report_readout_v1", judge["schema_version"])
        self.assertEqual("report_judge", judge["agent_name"])
        self.assertEqual("upside", judge["used_evidence"][0]["role"])
        self.assertEqual(100, sum(judge["evidence_weight"].values()))

    def test_outputs_validate_against_contracts(self) -> None:
        agents, judge = build_outputs(
            self.sample_evidence(),
            target_id="TARGET-SAMPLE-8697",
            stock_code="8697",
            company_name="日本取引所グループ",
            market="prime",
            themes=["取引所"],
            report_date="2025-03-28",
            run_id="ATR-TEST",
            run_at="2026-07-04T12:00:00+09:00",
        )
        agent_schema = json_load(ROOT / "system" / "contracts" / "agent_output.schema.json")
        judge_schema = json_load(ROOT / "system" / "contracts" / "report_judge.schema.json")
        JsonSchemaValidator(agent_schema).validate(agents)
        JsonSchemaValidator(judge_schema).validate(judge)


if __name__ == "__main__":
    unittest.main()
