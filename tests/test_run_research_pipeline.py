from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_research_pipeline import PipelineConfig, run_pipeline, run_dir  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class RunResearchPipelineTests(unittest.TestCase):
    def raw_artifact(self) -> dict:
        return self.raw_artifact_for_date("2025-03-28", 1580.0)

    def raw_artifact_for_date(self, date: str, close: float, *, code: str = "86970") -> dict:
        return {
            "schema_version": "jquants_raw_daily_quotes_v1",
            "provider": "jquants",
            "endpoint": "/equities/bars/daily",
            "fetched_at": "2026-07-04T12:00:00+09:00",
            "target_id": "TARGET-SAMPLE-8697",
            "code": code,
            "date": date,
            "status_code": 200,
            "request": {
                "url": f"https://api.jquants.com/v2/equities/bars/daily?code={code}&date={date.replace('-', '')}",
                "auth": "x-api-key",
                "code": code,
                "date": date.replace("-", ""),
            },
            "response": {
                "data": [
                    {
                        "Date": date,
                        "Code": code,
                        "O": close - 3,
                        "H": close + 5,
                        "L": close - 8,
                        "C": close,
                        "Vo": 4604900.0,
                        "Va": 7282456700.0,
                        "AdjC": close,
                        "AdjFactor": 1.0,
                    }
                ]
            },
            "summary": {
                "top_level_keys": ["data"],
                "row_count": 1,
                "first_row_keys": ["Date", "Code", "O", "C"],
            },
        }

    def edinet_raw_artifact(self) -> dict:
        return {
            "schema_version": "edinet_raw_documents_v1",
            "provider": "edinet",
            "endpoint": "/documents.json",
            "fetched_at": "2026-07-04T12:00:00+09:00",
            "target_id": "TARGET-SAMPLE-8697",
            "date": "2025-03-28",
            "doc_type": "2",
            "status_code": 200,
            "request": {
                "url": "https://api.edinet-fsa.go.jp/api/v2/documents.json?date=2025-03-28&type=2&Subscription-Key=REDACTED",
                "auth": "Subscription-Key query parameter",
                "date": "2025-03-28",
                "type": "2",
            },
            "response": {
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
            },
            "summary": {"result_count": 1},
        }

    def news_raw_artifact(self) -> dict:
        return {
            "schema_version": "newsapi_raw_articles_v1",
            "provider": "newsapi",
            "endpoint": "/everything",
            "fetched_at": "2026-07-04T12:00:00+09:00",
            "target_id": "TARGET-SAMPLE-8697",
            "query": "JPX",
            "date": "2025-03-28",
            "status_code": 200,
            "request": {
                "url": "https://newsapi.org/v2/everything?q=JPX",
                "auth": "X-Api-Key header",
                "query": "JPX",
            },
            "response": {
                "status": "ok",
                "totalResults": 1,
                "articles": [
                    {
                        "source": {"id": "example", "name": "Example News"},
                        "author": "Reporter",
                        "title": "JPX market systems update",
                        "description": "Short public summary.",
                        "url": "https://example.com/article",
                        "publishedAt": "2025-03-28T01:00:00Z",
                        "content": "Short public content excerpt.",
                    }
                ],
            },
            "summary": {"article_count": 1},
        }

    def rss_news_raw_artifact(self) -> dict:
        artifact = self.news_raw_artifact()
        artifact["schema_version"] = "rss_raw_articles_v1"
        artifact["provider"] = "rss"
        artifact["endpoint"] = "https://news.google.com/rss/search?q=JPX"
        artifact["request"]["auth"] = "none"
        return artifact

    def ir_raw_artifact(self) -> dict:
        return {
            "schema_version": "ir_raw_page_v1",
            "provider": "official_ir",
            "endpoint": "url",
            "fetched_at": "2026-07-04T12:00:00+09:00",
            "target_id": "TARGET-SAMPLE-8697",
            "company_name": "日本取引所グループ",
            "url": "https://www.jpx.co.jp/corporate/investor-relations/",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "metadata": {
                "title": "IR情報 | 日本取引所グループ",
                "description": "日本取引所グループのIR情報です。",
                "snippet": "株主・投資家向けの公式情報を掲載しています。",
            },
            "summary": {
                "has_title": True,
                "has_description": True,
                "has_snippet": True,
            },
        }

    def test_pipeline_writes_run_artifacts_with_mock_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            write_json(raw_path, self.raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                publish_reports=False,
            )
            manifest = run_pipeline(config)
            directory = run_dir(config)
            self.assertEqual("ok", manifest["status"])
            self.assertTrue((directory / "pipeline_manifest.json").is_file())
            self.assertTrue((directory / "evidence.json").is_file())
            self.assertTrue((directory / "agent_outputs.json").is_file())
            self.assertTrue((directory / "report_judge.json").is_file())
            self.assertTrue((directory / "health.json").is_file())
            self.assertEqual(3, len(list((directory / "reports").glob("*"))))
            health = json.loads((directory / "health.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", health["overall_status"])
            self.assertEqual(2, health["stats"]["evidence_total"])
            self.assertTrue((directory / "derived" / "jquants" / "indicators.json").is_file())

    def test_pipeline_uses_history_raws_for_moving_average(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_paths = []
            for index, date in enumerate(["2025-03-24", "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28"], start=1):
                path = root / f"raw_{date}.json"
                write_json(path, self.raw_artifact_for_date(date, 1500 + index * 10))
                raw_paths.append(path)
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_paths[-1],
                history_raws=tuple(raw_paths[:-1]),
                publish_reports=False,
            )
            run_pipeline(config)
            directory = run_dir(config)
            indicators = json.loads((directory / "derived" / "jquants" / "indicators.json").read_text(encoding="utf-8"))
            self.assertTrue(indicators["quality"]["has_ma_5"])
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            derived = [item for item in evidence if item["source"]["source_name"] == "J-Quants derived indicators"][0]
            self.assertIn("ma_5", derived["content"]["metrics"])

    def test_pipeline_can_merge_edinet_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            edinet_raw_path = root / "input_edinet_raw.json"
            write_json(raw_path, self.raw_artifact())
            write_json(edinet_raw_path, self.edinet_raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                include_edinet=True,
                edinet_raw=edinet_raw_path,
                publish_reports=False,
            )
            run_pipeline(config)
            directory = run_dir(config)
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(3, len(evidence))
            self.assertEqual("disclosure_edinet", evidence[2]["source"]["source_type"])

    def test_pipeline_can_merge_news_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            news_raw_path = root / "input_news_raw.json"
            write_json(raw_path, self.raw_artifact())
            write_json(news_raw_path, self.news_raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                include_news=True,
                news_raw=news_raw_path,
                publish_reports=False,
            )
            run_pipeline(config)
            directory = run_dir(config)
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(3, len(evidence))
            self.assertEqual("news", evidence[2]["source"]["source_type"])
            health = json.loads((directory / "health.json").read_text(encoding="utf-8"))
            checks = [check for section in health["sections"] for check in section["checks"]]
            self.assertTrue(any(check["check_id"] == "news_evidence" and check["status"] == "ok" for check in checks))

    def test_pipeline_include_news_falls_back_to_rss_without_newsapi_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            write_json(raw_path, self.raw_artifact())

            def write_rss_raw(**kwargs) -> Path:
                path = kwargs["out_root"] / kwargs["date"] / kwargs["target_id"] / "rss_articles_raw.json"
                payload = self.rss_news_raw_artifact()
                payload["date"] = kwargs["date"]
                payload["target_id"] = kwargs["target_id"]
                write_json(path, payload)
                return path

            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                include_news=True,
                news_query="JPX",
                publish_reports=False,
            )
            with patch.dict("os.environ", {"NEWS_API_KEY": ""}, clear=False):
                with patch("run_research_pipeline.NEWS_RSS_FETCH.fetch_and_save", side_effect=write_rss_raw) as rss_fetch:
                    run_pipeline(config)
            self.assertTrue(rss_fetch.called)
            directory = run_dir(config)
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual("news", evidence[2]["source"]["source_type"])

    def test_pipeline_can_merge_ir_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            ir_raw_path = root / "input_ir_raw.json"
            write_json(raw_path, self.raw_artifact())
            write_json(ir_raw_path, self.ir_raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                include_ir=True,
                ir_raw=ir_raw_path,
                publish_reports=False,
            )
            run_pipeline(config)
            directory = run_dir(config)
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(3, len(evidence))
            self.assertEqual("ir", evidence[2]["source"]["source_type"])
            health = json.loads((directory / "health.json").read_text(encoding="utf-8"))
            checks = [check for section in health["sections"] for check in section["checks"]]
            self.assertTrue(any(check["check_id"] == "ir_evidence" and check["status"] == "ok" for check in checks))

    def test_pipeline_can_merge_relative_comparison_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            benchmark_raw_path = root / "benchmark_raw.json"
            write_json(raw_path, self.raw_artifact_for_date("2025-03-28", 1580.0))
            write_json(benchmark_raw_path, self.raw_artifact_for_date("2025-03-28", 3050.0, code="13060"))
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                comparison_raws=(f"SectorETF={benchmark_raw_path}",),
                publish_reports=False,
            )
            run_pipeline(config)
            directory = run_dir(config)
            evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(3, len(evidence))
            self.assertEqual("market_supply", evidence[2]["source"]["source_type"])
            self.assertTrue((directory / "derived" / "jquants" / "relative_comparison.json").is_file())
            health = json.loads((directory / "health.json").read_text(encoding="utf-8"))
            checks = [check for section in health["sections"] for check in section["checks"]]
            self.assertTrue(any(check["check_id"] == "jquants_relative_comparison" and check["status"] == "ok" for check in checks))

    def test_pipeline_can_run_sequential_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            write_json(raw_path, self.raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                publish_reports=False,
                agent_execution="sequential",
            )
            manifest = run_pipeline(config)
            directory = run_dir(config)
            self.assertEqual("sequential", manifest["agent_execution"])
            self.assertTrue((directory / "agent_steps" / "search_design.json").is_file())
            self.assertTrue((directory / "agent_sequence_manifest.json").is_file())
            self.assertTrue((directory / "agent_sequence_health.json").is_file())
            self.assertTrue((directory / "agent_sequence_status.json").is_file())
            self.assertIn("agent_sequence_health", manifest["paths"])
            self.assertIn("agent_sequence_status", manifest["paths"])
            self.assertTrue((directory / "reports" / "2025-03-28_8697_close.html").is_file())

    def test_pipeline_error_health_preserves_built_evidence_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            write_json(raw_path, self.raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                publish_reports=False,
            )
            with patch("run_research_pipeline.run_llm_step", side_effect=RuntimeError("agent down")):
                with self.assertRaises(RuntimeError):
                    run_pipeline(config)
            directory = run_dir(config)
            health = json.loads((directory / "health.json").read_text(encoding="utf-8"))
            manifest = json.loads((directory / "pipeline_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("error", health["overall_status"])
            self.assertEqual(2, health["stats"]["evidence_total"])
            self.assertEqual("error", manifest["status"])

    def test_pipeline_error_manifest_preserves_agent_sequence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "input_raw.json"
            write_json(raw_path, self.raw_artifact())
            config = PipelineConfig(
                target_id="TARGET-SAMPLE-8697",
                code="86970",
                stock_code="8697",
                company_name="日本取引所グループ",
                date="2025-03-28",
                bucket="morning",
                market="prime",
                themes=("取引所",),
                provider="mock",
                model="deterministic-baseline",
                out_root=root / "runs",
                raw=raw_path,
                publish_reports=False,
                agent_execution="sequential",
            )

            def fail_after_status(config: PipelineConfig, evidence_path: Path, output_dir: Path, run_id: str) -> None:
                status_path = output_dir / "agent_sequence_status.json"
                write_json(
                    status_path,
                    {
                        "schema_version": "agent_sequence_status_v1",
                        "run_id": run_id,
                        "updated_at": "2026-07-04T12:00:00+09:00",
                        "target_id": config.target_id,
                        "provider": config.provider,
                        "model": config.model,
                        "status": "error",
                        "current_step": None,
                        "failed_step": "search_design",
                        "completed_steps": [],
                        "resumed_steps": [],
                        "steps": [],
                        "error": "agent down",
                    },
                )
                (output_dir / "agent_steps").mkdir(parents=True, exist_ok=True)
                raise RuntimeError("agent down")

            with patch("run_research_pipeline.run_llm_step", side_effect=fail_after_status):
                with self.assertRaises(RuntimeError):
                    run_pipeline(config)
            directory = run_dir(config)
            manifest = json.loads((directory / "pipeline_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("error", manifest["status"])
            self.assertIn("agent_sequence_status", manifest["paths"])
            self.assertIn("agent_steps_dir", manifest["paths"])


if __name__ == "__main__":
    unittest.main()
