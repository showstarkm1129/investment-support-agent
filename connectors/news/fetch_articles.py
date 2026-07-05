#!/usr/bin/env python3
"""Fetch public news article metadata from NewsAPI and save a raw artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_flow import configured_env_file, load_env_file  # noqa: E402


JST = timezone(timedelta(hours=9))
NEWSAPI_BASE_URL = "https://newsapi.org/v2"


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value != ""})
    return f"{base_url}{path}?{query}" if query else f"{base_url}{path}"


def sanitize_text(text: str, secrets: list[str]) -> str:
    sanitized = text
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "REDACTED")
    return sanitized


def request_json(*, url: str, api_key: str, timeout: int) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"X-Api-Key": api_key}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


def articles_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    articles = payload.get("articles")
    return [item for item in articles if isinstance(item, dict)] if isinstance(articles, list) else []


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    articles = articles_from_payload(payload)
    return {
        "top_level_keys": sorted(payload.keys()),
        "status": payload.get("status"),
        "total_results": payload.get("totalResults"),
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
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "newsapi_raw_articles_v1",
        "provider": "newsapi",
        "endpoint": "/everything",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "query": query,
        "date": date,
        "status_code": status_code,
        "request": {
            "url": request_url,
            "auth": "X-Api-Key header",
            "query": query,
        },
        "response": payload,
        "summary": summarize_payload(payload),
    }


def error_artifact(*, target_id: str, query: str, date: str, request_url: str, error: str) -> dict[str, Any]:
    return {
        "schema_version": "newsapi_raw_articles_error_v1",
        "provider": "newsapi",
        "endpoint": "/everything",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "query": query,
        "date": date,
        "status": "error",
        "request": {
            "url": request_url,
            "auth": "X-Api-Key header",
            "query": query,
        },
        "error": error,
    }


def output_path(*, out_root: Path, target_id: str, date: str, error: bool = False) -> Path:
    suffix = "error" if error else "raw"
    return out_root / date / target_id / f"articles_{date}_{suffix}.json"


def assert_no_secret_leak(path: Path, secrets: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    leaked = [secret for secret in secrets if secret and secret in text]
    if leaked:
        raise RuntimeError(f"{path}: secret value leaked into raw artifact")


def fetch_and_save(
    *,
    api_key: str,
    target_id: str,
    query: str,
    date: str,
    out_root: Path,
    language: str,
    sort_by: str,
    page_size: int,
    timeout: int,
    base_url: str = NEWSAPI_BASE_URL,
) -> Path:
    params = {
        "q": query,
        "from": date,
        "to": date,
        "language": language,
        "sortBy": sort_by,
        "pageSize": str(page_size),
    }
    url = build_url(base_url, "/everything", params)
    redacted_url = sanitize_text(url, [api_key])
    try:
        status_code, payload = request_json(url=url, api_key=api_key, timeout=timeout)
        artifact = raw_artifact(
            target_id=target_id,
            query=query,
            date=date,
            status_code=status_code,
            request_url=redacted_url,
            payload=payload,
        )
        path = output_path(out_root=out_root, target_id=target_id, date=date)
        write_json(path, artifact)
        assert_no_secret_leak(path, [api_key])
        return path
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        artifact = error_artifact(target_id=target_id, query=query, date=date, request_url=redacted_url, error=f"HTTP {exc.code}: {body[:1000]}")
    except Exception as exc:
        artifact = error_artifact(target_id=target_id, query=query, date=date, request_url=redacted_url, error=str(exc))
    path = output_path(out_root=out_root, target_id=target_id, date=date, error=True)
    write_json(path, artifact)
    assert_no_secret_leak(path, [api_key])
    raise RuntimeError(f"NewsAPI fetch failed; error artifact written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch NewsAPI /everything article metadata.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/raw/news")
    parser.add_argument("--language", default="en")
    parser.add_argument("--sort-by", default="publishedAt", choices=["relevancy", "popularity", "publishedAt"])
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    env_file = args.env_file if args.env_file else configured_env_file()
    loaded_keys = load_env_file(env_file)
    api_key = os.environ.get("NEWS_API_KEY", "")
    print(f"env_file={env_file}")
    print(f"loaded_env_keys={sorted(key for key in loaded_keys if key == 'NEWS_API_KEY')}")
    print(f"NEWS_API_KEY_present={bool(api_key)}")
    if not api_key:
        raise RuntimeError("NEWS_API_KEY is not set")
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    path = fetch_and_save(
        api_key=api_key,
        target_id=args.target_id,
        query=args.query,
        date=args.date,
        out_root=out_root,
        language=args.language,
        sort_by=args.sort_by,
        page_size=args.page_size,
        timeout=args.timeout,
    )
    print(f"raw_path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
