#!/usr/bin/env python3
"""Fetch EDINET document metadata and save a raw artifact."""

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
EDINET_BASE_URL = "https://api.edinet-fsa.go.jp/api/v2"


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{base_url}{path}?{query}" if query else f"{base_url}{path}"


def sanitize_url(url: str, secrets: list[str]) -> str:
    sanitized = url
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "REDACTED")
    return sanitized


def request_json(*, url: str, timeout: int) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


def rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results")
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = rows_from_payload(payload)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "top_level_keys": sorted(payload.keys()),
        "metadata_keys": sorted(metadata.keys()),
        "result_count": len(rows),
        "first_result_keys": sorted(rows[0].keys()) if rows else [],
    }


def raw_artifact(
    *,
    target_id: str,
    date: str,
    doc_type: str,
    status_code: int,
    request_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "edinet_raw_documents_v1",
        "provider": "edinet",
        "endpoint": "/documents.json",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "date": date,
        "doc_type": doc_type,
        "status_code": status_code,
        "request": {
            "url": request_url,
            "auth": "Subscription-Key query parameter",
            "date": date,
            "type": doc_type,
        },
        "response": payload,
        "summary": summarize_payload(payload),
    }


def error_artifact(*, target_id: str, date: str, doc_type: str, request_url: str, error: str) -> dict[str, Any]:
    return {
        "schema_version": "edinet_raw_documents_error_v1",
        "provider": "edinet",
        "endpoint": "/documents.json",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "date": date,
        "doc_type": doc_type,
        "status": "error",
        "request": {
            "url": request_url,
            "auth": "Subscription-Key query parameter",
            "date": date,
            "type": doc_type,
        },
        "error": error,
    }


def output_path(*, out_root: Path, target_id: str, date: str, error: bool = False) -> Path:
    suffix = "error" if error else "raw"
    return out_root / date / target_id / f"documents_{date}_{suffix}.json"


def assert_no_secret_leak(path: Path, secrets: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    leaked = [secret for secret in secrets if secret and secret in text]
    if leaked:
        raise RuntimeError(f"{path}: secret value leaked into raw artifact")


def fetch_and_save(
    *,
    api_key: str,
    target_id: str,
    date: str,
    out_root: Path,
    doc_type: str,
    timeout: int,
    base_url: str = EDINET_BASE_URL,
) -> Path:
    params = {"date": date, "type": doc_type, "Subscription-Key": api_key}
    url = build_url(base_url, "/documents.json", params)
    redacted_url = sanitize_url(url, [api_key])
    try:
        status_code, payload = request_json(url=url, timeout=timeout)
        artifact = raw_artifact(
            target_id=target_id,
            date=date,
            doc_type=doc_type,
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
        artifact = error_artifact(target_id=target_id, date=date, doc_type=doc_type, request_url=redacted_url, error=f"HTTP {exc.code}: {body[:1000]}")
    except Exception as exc:
        artifact = error_artifact(target_id=target_id, date=date, doc_type=doc_type, request_url=redacted_url, error=str(exc))
    path = output_path(out_root=out_root, target_id=target_id, date=date, error=True)
    write_json(path, artifact)
    assert_no_secret_leak(path, [api_key])
    raise RuntimeError(f"EDINET fetch failed; error artifact written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch EDINET document metadata into data/raw.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--type", default="2", dest="doc_type")
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/raw/edinet")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    env_file = args.env_file if args.env_file else configured_env_file()
    loaded_keys = load_env_file(env_file)
    api_key = os.environ.get("EDINET_API_KEY", "")
    print(f"env_file={env_file}")
    print(f"loaded_env_keys={sorted(key for key in loaded_keys if key == 'EDINET_API_KEY')}")
    print(f"EDINET_API_KEY_present={bool(api_key)}")
    if not api_key:
        raise RuntimeError("EDINET_API_KEY is not set")
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    path = fetch_and_save(
        api_key=api_key,
        target_id=args.target_id,
        date=args.date,
        out_root=out_root,
        doc_type=args.doc_type,
        timeout=args.timeout,
    )
    print(f"raw_path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
