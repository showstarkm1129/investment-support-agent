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


news_fetch = load_module("news_fetch_articles", ROOT / "connectors" / "news" / "fetch_articles.py")
news_rss = load_module("news_fetch_rss", ROOT / "connectors" / "news" / "fetch_rss.py")
news_build = load_module("news_build_evidence", ROOT / "connectors" / "news" / "build_evidence.py")


class NewsConnectorTests(unittest.TestCase):
    def sample_payload(self) -> dict:
        return {
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
        }

    def test_summarize_payload_counts_articles(self) -> None:
        summary = news_fetch.summarize_payload(self.sample_payload())
        self.assertEqual(1, summary["article_count"])
        self.assertEqual("ok", summary["status"])

    def test_raw_artifact_redacts_auth_from_request(self) -> None:
        artifact = news_fetch.raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            query="JPX",
            date="2025-03-28",
            status_code=200,
            request_url="https://newsapi.org/v2/everything?q=JPX",
            payload=self.sample_payload(),
        )
        self.assertEqual("X-Api-Key header", artifact["request"]["auth"])

    def test_evidence_from_raw_creates_news_evidence(self) -> None:
        raw = news_fetch.raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            query="JPX",
            date="2025-03-28",
            status_code=200,
            request_url="https://newsapi.org/v2/everything?q=JPX",
            payload=self.sample_payload(),
        )
        evidence = news_build.evidence_from_raw(
            raw,
            stock_code="8697",
            company_name="日本取引所グループ",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("E20250328-201", item["evidence_id"])
        self.assertEqual("news", item["source"]["source_type"])
        self.assertEqual("Example News", item["source"]["source_name"])
        self.assertEqual("2025-03-28T01:00:00+00:00", item["identity"]["published_at"])

    def test_rss_raw_can_be_converted_to_news_evidence(self) -> None:
        articles = [
            {
                "source": {"id": "https://example.com", "name": "RSS Source"},
                "author": None,
                "title": "JPX RSS item",
                "description": "RSS description.",
                "url": "https://example.com/rss-item",
                "publishedAt": "2025-03-28T00:00:00+00:00",
                "content": None,
            }
        ]
        raw = news_rss.raw_artifact(
            target_id="TARGET-SAMPLE-8697",
            query="JPX",
            date="2025-03-28",
            status_code=200,
            request_url="https://news.google.com/rss/search?q=JPX",
            articles=articles,
        )
        evidence = news_build.evidence_from_raw(
            raw,
            stock_code="8697",
            company_name="日本取引所グループ",
            collected_at="2026-07-04T12:00:00+09:00",
        )
        self.assertEqual(1, len(evidence))
        self.assertEqual("E20250328-201", evidence[0]["evidence_id"])
        self.assertEqual("RSS Source", evidence[0]["source"]["source_name"])


if __name__ == "__main__":
    unittest.main()
