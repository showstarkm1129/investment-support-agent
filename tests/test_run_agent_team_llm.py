from __future__ import annotations

import json
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_agent_team_llm import extract_json_text, parse_llm_payload, provider_text, validate_payload  # noqa: E402
from build_agent_team_readout import build_outputs  # noqa: E402


class RunAgentTeamLlmTests(unittest.TestCase):
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

    def test_extract_json_text_from_fence(self) -> None:
        self.assertEqual('{"ok": true}', extract_json_text('```json\n{"ok": true}\n```'))

    def test_parse_llm_payload_from_prefixed_text(self) -> None:
        self.assertEqual({"ok": True}, parse_llm_payload('Here:\n{"ok": true}\nDone'))

    def test_parse_llm_payload_from_codex_logs(self) -> None:
        text = 'codex\\n{"ok": true}\\ntokens used\\n123\\n{"ignored": true}'
        self.assertEqual({"ok": True}, parse_llm_payload(text))

    def test_provider_text_openai_response_shape(self) -> None:
        response = {"output": [{"content": [{"type": "output_text", "text": "{\"ok\": true}"}]}]}
        self.assertEqual('{"ok": true}', provider_text(response, "openai_api"))

    def test_validate_payload_accepts_contract_shaped_baseline(self) -> None:
        agents, judge = build_outputs(
            self.sample_evidence(),
            target_id="TARGET-SAMPLE-8697",
            stock_code="8697",
            company_name="日本取引所グループ",
            market="prime",
            themes=["取引所"],
            report_date="2025-03-28",
            run_id="LLM-TEST",
            run_at="2026-07-04T12:00:00+09:00",
        )
        valid_agents, valid_judge = validate_payload({"agent_outputs": agents, "report_judge": judge}, self.sample_evidence())
        self.assertEqual("agent_outputs_bundle_v1", valid_agents["schema_version"])
        self.assertEqual("report_readout_v1", valid_judge["schema_version"])

    def test_validate_payload_rejects_unknown_evidence_reference(self) -> None:
        agents, judge = build_outputs(
            self.sample_evidence(),
            target_id="TARGET-SAMPLE-8697",
            stock_code="8697",
            company_name="日本取引所グループ",
            market="prime",
            themes=["取引所"],
            report_date="2025-03-28",
            run_id="LLM-TEST",
            run_at="2026-07-04T12:00:00+09:00",
        )
        agents = json.loads(json.dumps(agents))
        agents["agent_outputs"][0]["evidence_ids"] = ["E20990101-999"]
        with self.assertRaises(ValueError):
            validate_payload({"agent_outputs": agents, "report_judge": judge}, self.sample_evidence())


if __name__ == "__main__":
    unittest.main()
