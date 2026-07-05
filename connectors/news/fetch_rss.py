#!/usr/bin/env python3
"""Fetch public RSS/Atom news metadata and save a raw artifact."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JST = timezone(timedelta(hours=9))
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_google_news_url(query: str, language: str) -> str:
    if language.lower().startswith("ja"):
        params = {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return f"{GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(params)}"


def request_xml(*, url: str, timeout: int) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "investment-support-agent/0.1"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, raw.decode(charset, errors="replace")


def text_of(element: ET.Element, name: str) -> str:
    found = element.find(name)
    return " ".join((found.text or "").split()) if found is not None else ""


def normalize_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except Exception:
        return value


def parse_rss_articles(xml_text: str, *, max_items: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:max_items]:
        source = item.find("source")
        articles.append(
            {
                "source": {
                    "id": source.get("url") if source is not None else None,
                    "name": " ".join((source.text or "").split()) if source is not None else "RSS",
                },
                "author": None,
                "title": text_of(item, "title") or "RSS news item",
                "description": text_of(item, "description") or None,
                "url": text_of(item, "link") or None,
                "publishedAt": normalize_datetime(text_of(item, "pubDate")),
                "content": None,
            }
        )
    return articles


def summarize_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "article_count": len(articles),
        "first_article_keys": sorted(articles[0].keys()) if articles else [],
    }


def raw_artifact(
    *,
    target_id: str,
    query: str,
    date: str,
    status_code: int,
    request_url: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "rss_raw_articles_v1",
        "provider": "rss",
        "endpoint": request_url,
        "fetched_at": now_jst(),
        "target_id": target_id,
        "query": query,
        "date": date,
        "status_code": status_code,
        "request": {
            "url": request_url,
            "auth": "none",
            "query": query,
        },
        "response": {
            "status": "ok",
            "totalResults": len(articles),
            "articles": articles,
        },
        "summary": summarize_articles(articles),
    }


def output_path(*, out_root: Path, target_id: str, date: str) -> Path:
    return out_root / date / target_id / f"rss_articles_{date}_raw.json"


def fetch_and_save(
    *,
    target_id: str,
    query: str,
    date: str,
    out_root: Path,
    language: str,
    timeout: int,
    max_items: int = 10,
    rss_url: str = "",
) -> Path:
    url = rss_url or build_google_news_url(query, language)
    status_code, xml_text = request_xml(url=url, timeout=timeout)
    articles = parse_rss_articles(xml_text, max_items=max_items)
    artifact = raw_artifact(
        target_id=target_id,
        query=query,
        date=date,
        status_code=status_code,
        request_url=url,
        articles=articles,
    )
    path = output_path(out_root=out_root, target_id=target_id, date=date)
    write_json(path, artifact)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RSS/Atom news metadata.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/raw/news")
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--rss-url", default="")
    args = parser.parse_args()

    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    path = fetch_and_save(
        target_id=args.target_id,
        query=args.query,
        date=args.date,
        out_root=out_root,
        language=args.language,
        timeout=args.timeout,
        max_items=args.max_items,
        rss_url=args.rss_url,
    )
    print(f"raw_path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
