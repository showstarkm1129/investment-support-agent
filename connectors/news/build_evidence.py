#!/usr/bin/env python3
"""Build Evidence JSON from NewsAPI article metadata."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JST = timezone(timedelta(hours=9))


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compact_date(value: str) -> str:
    return value.replace("-", "")


def articles_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    articles = response.get("articles") if isinstance(response, dict) else []
    return [item for item in articles if isinstance(item, dict)] if isinstance(articles, list) else []


def published_at(article: dict[str, Any], fallback_date: str) -> str:
    raw = str(article.get("publishedAt") or "").strip()
    if raw:
        normalized = raw.replace("Z", "+00:00")
        if "+" in normalized[-6:] or "-" in normalized[-6:]:
            return normalized
        return f"{normalized}+00:00"
    return f"{fallback_date}T00:00:00+09:00"


def source_name(article: dict[str, Any]) -> str:
    source = article.get("source") if isinstance(article.get("source"), dict) else {}
    return str(source.get("name") or "NewsAPI")


def short_excerpt(article: dict[str, Any]) -> str | None:
    for key in ["description", "content"]:
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return None


def evidence_from_raw(
    raw: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    max_items: int = 10,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if raw.get("schema_version") not in {"newsapi_raw_articles_v1", "rss_raw_articles_v1"}:
        raise ValueError("raw artifact must have schema_version newsapi_raw_articles_v1 or rss_raw_articles_v1")
    collected = collected_at or now_jst()
    target_id = str(raw.get("target_id") or "")
    date = str(raw.get("date") or collected[:10])
    articles = articles_from_raw(raw)[:max_items]
    evidence = []
    for index, article in enumerate(articles, start=201):
        title = str(article.get("title") or "News item")
        url = article.get("url") if isinstance(article.get("url"), str) else None
        source = source_name(article)
        excerpt = short_excerpt(article)
        summary = f"{date}に{source}で関連ニュースを確認。タイトル: {title}"
        if excerpt:
            summary += f" 概要: {excerpt[:180]}"
        evidence.append(
            {
                "schema_version": "evidence_v1",
                "evidence_id": f"E{compact_date(date)}-{index:03d}",
                "identity": {
                    "target_id": target_id,
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "collected_at": collected,
                    "published_at": published_at(article, date),
                },
                "source": {
                    "source_type": "news",
                    "source_name": source,
                    "source_url": url,
                    "source_reliability": "C",
                    "save_policy": "summary_and_short_excerpt",
                },
                "content": {
                    "title": title,
                    "summary": summary,
                    "excerpt": excerpt,
                    "metrics": {
                        "author": article.get("author"),
                        "source_id": (article.get("source") or {}).get("id") if isinstance(article.get("source"), dict) else None,
                        "url": url,
                    },
                },
                "evaluation": {
                    "directness": "medium",
                    "freshness": "high",
                    "impact_level": "medium",
                    "direction_hint": "unknown",
                    "related_topics": ["ニュース", "外部報道"],
                    "hypothesis_impact": "公開ニュースの存在確認であり、本文精査前のため方向性はunknownとして扱う。",
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
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Evidence JSON from NewsAPI raw articles.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()

    raw_path = args.raw if args.raw.is_absolute() else ROOT / args.raw
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    raw = load_json(raw_path)
    evidence = evidence_from_raw(raw, stock_code=args.stock_code, company_name=args.company_name, max_items=args.max_items)
    write_json(out_path, evidence)
    print(f"evidence_path={out_path}")
    print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
