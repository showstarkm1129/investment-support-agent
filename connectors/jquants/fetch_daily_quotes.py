#!/usr/bin/env python3
"""Fetch J-Quants daily price data and save a raw artifact."""

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
JQUANTS_BASE_URL = "https://api.jquants.com/v2"


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def normalize_api_date(value: str) -> str:
    return value.replace("-", "")


def display_date(value: str) -> str:
    compact = normalize_api_date(value)
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return value


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{base_url}{path}?{query}" if query else f"{base_url}{path}"


def sanitize_url(url: str, secret_values: list[str]) -> str:
    sanitized = url
    for value in secret_values:
        if value:
            sanitized = sanitized.replace(value, "REDACTED")
    return sanitized


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def request_json(*, url: str, api_key: str, timeout: int) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"x-api-key": api_key}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


def rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["data", "daily_quotes", "bars"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = rows_from_payload(payload)
    return {
        "top_level_keys": sorted(payload.keys()),
        "row_count": len(rows),
        "first_row_keys": sorted(rows[0].keys()) if rows else [],
    }


def raw_artifact(
    *,
    target_id: str,
    code: str,
    date: str,
    status_code: int,
    request_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "jquants_raw_daily_quotes_v1",
        "provider": "jquants",
        "endpoint": "/equities/bars/daily",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "code": code,
        "date": display_date(date),
        "status_code": status_code,
        "request": {
            "url": request_url,
            "auth": "x-api-key",
            "code": code,
            "date": normalize_api_date(date),
        },
        "response": payload,
        "summary": summarize_payload(payload),
    }


def error_artifact(
    *,
    target_id: str,
    code: str,
    date: str,
    request_url: str,
    error: str,
) -> dict[str, Any]:
    return {
        "schema_version": "jquants_raw_daily_quotes_error_v1",
        "provider": "jquants",
        "endpoint": "/equities/bars/daily",
        "fetched_at": now_jst(),
        "target_id": target_id,
        "code": code,
        "date": display_date(date),
        "status": "error",
        "request": {
            "url": request_url,
            "auth": "x-api-key",
            "code": code,
            "date": normalize_api_date(date),
        },
        "error": error,
    }


def output_path(*, out_root: Path, target_id: str, date: str, code: str, error: bool = False) -> Path:
    suffix = "error" if error else "raw"
    return out_root / display_date(date) / target_id / f"daily_quotes_{code}_{normalize_api_date(date)}_{suffix}.json"


def assert_no_secret_leak(path: Path, secrets: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    leaked = [secret for secret in secrets if secret and secret in text]
    if leaked:
        raise RuntimeError(f"{path}: secret value leaked into raw artifact")


def fetch_and_save(
    *,
    api_key: str,
    target_id: str,
    code: str,
    date: str,
    out_root: Path,
    timeout: int,
    base_url: str = JQUANTS_BASE_URL,
) -> Path:
    params = {"code": code, "date": normalize_api_date(date)}
    url = build_url(base_url, "/equities/bars/daily", params)
    redacted_url = sanitize_url(url, [api_key])
    try:
        status_code, payload = request_json(url=url, api_key=api_key, timeout=timeout)
        artifact = raw_artifact(
            target_id=target_id,
            code=code,
            date=date,
            status_code=status_code,
            request_url=redacted_url,
            payload=payload,
        )
        path = output_path(out_root=out_root, target_id=target_id, date=date, code=code)
        write_json(path, artifact)
        assert_no_secret_leak(path, [api_key])
        return path
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        artifact = error_artifact(
            target_id=target_id,
            code=code,
            date=date,
            request_url=redacted_url,
            error=f"HTTP {exc.code}: {body[:1000]}",
        )
    except Exception as exc:
        artifact = error_artifact(
            target_id=target_id,
            code=code,
            date=date,
            request_url=redacted_url,
            error=str(exc),
        )
    path = output_path(out_root=out_root, target_id=target_id, date=date, code=code, error=True)
    write_json(path, artifact)
    assert_no_secret_leak(path, [api_key])
    raise RuntimeError(f"J-Quants fetch failed; error artifact written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch J-Quants daily quotes into data/raw.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--code", required=True, help="J-Quants issue code, e.g. 86970.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD or YYYYMMDD.")
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/raw/jquants")
    parser.add_argument("--env-file", type=Path, help="Env file containing JQUANTS_API_KEY.")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    env_file = args.env_file if args.env_file else configured_env_file()
    loaded_keys = load_env_file(env_file)
    api_key = os.environ.get("JQUANTS_API_KEY", "")
    print(f"env_file={env_file}")
    print(f"loaded_env_keys={sorted(key for key in loaded_keys if key == 'JQUANTS_API_KEY')}")
    print(f"JQUANTS_API_KEY_present={bool(api_key)}")
    if not api_key:
        print("ERROR: JQUANTS_API_KEY is not set", file=sys.stderr)
        return 1

    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    try:
        path = fetch_and_save(
            api_key=api_key,
            target_id=args.target_id,
            code=args.code,
            date=args.date,
            out_root=out_root,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"raw_path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
