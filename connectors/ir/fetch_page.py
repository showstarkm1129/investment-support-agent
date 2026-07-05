#!/usr/bin/env python3
"""Fetch official IR page metadata and save a raw artifact."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JST = timezone(timedelta(hours=9))


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if lower == "title":
            self.in_title = True
        if lower == "meta":
            attrs_map = {key.lower(): value or "" for key, value in attrs}
            if attrs_map.get("name", "").lower() == "description" and attrs_map.get("content"):
                self.meta_description = attrs_map["content"].strip()

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if lower == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif self._skip_depth == 0 and len(self.text_parts) < 80:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def snippet(self) -> str:
        return " ".join(self.text_parts).strip()[:1000]


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def request_html(*, url: str, timeout: int) -> tuple[int, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "investment-support-agent/0.1"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, content_type, raw.decode(charset, errors="replace")


def parse_metadata(html: str) -> dict[str, str | None]:
    parser = MetadataParser()
    parser.feed(html)
    return {
        "title": parser.title or None,
        "description": parser.meta_description,
        "snippet": parser.snippet or None,
    }


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug[:80] or "ir_page"


def raw_artifact(
    *,
    target_id: str,
    company_name: str,
    url: str,
    status_code: int,
    content_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "ir_raw_page_v1",
        "provider": "official_ir",
        "endpoint": "url",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "company_name": company_name,
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "metadata": metadata,
        "summary": {
            "has_title": bool(metadata.get("title")),
            "has_description": bool(metadata.get("description")),
            "has_snippet": bool(metadata.get("snippet")),
        },
    }


def error_artifact(*, target_id: str, company_name: str, url: str, error: str) -> dict[str, Any]:
    return {
        "schema_version": "ir_raw_page_error_v1",
        "provider": "official_ir",
        "endpoint": "url",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "company_name": company_name,
        "url": url,
        "status": "error",
        "error": error,
    }


def output_path(*, out_root: Path, target_id: str, date: str, url: str, error: bool = False) -> Path:
    suffix = "error" if error else "raw"
    return out_root / date / target_id / f"{safe_slug(url)}_{suffix}.json"


def fetch_and_save(
    *,
    target_id: str,
    company_name: str,
    url: str,
    date: str,
    out_root: Path,
    timeout: int,
) -> Path:
    try:
        status_code, content_type, html = request_html(url=url, timeout=timeout)
        artifact = raw_artifact(
            target_id=target_id,
            company_name=company_name,
            url=url,
            status_code=status_code,
            content_type=content_type,
            metadata=parse_metadata(html),
        )
        path = output_path(out_root=out_root, target_id=target_id, date=date, url=url)
        write_json(path, artifact)
        return path
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        artifact = error_artifact(target_id=target_id, company_name=company_name, url=url, error=f"HTTP {exc.code}: {body[:1000]}")
    except Exception as exc:
        artifact = error_artifact(target_id=target_id, company_name=company_name, url=url, error=str(exc))
    path = output_path(out_root=out_root, target_id=target_id, date=date, url=url, error=True)
    write_json(path, artifact)
    raise RuntimeError(f"IR fetch failed; error artifact written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch official IR page metadata.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/raw/ir")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    path = fetch_and_save(
        target_id=args.target_id,
        company_name=args.company_name,
        url=args.url,
        date=args.date,
        out_root=out_root,
        timeout=args.timeout,
    )
    print(f"raw_path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
