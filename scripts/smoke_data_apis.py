#!/usr/bin/env python3
"""Smoke test J-Quants and EDINET API connectivity without exposing secrets."""

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

from run_flow import configured_env_file, load_env_file


ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
JQUANTS_BASE_URL = "https://api.jquants.com/v2"
EDINET_BASE_URL = "https://api.edinet-fsa.go.jp/api/v2"


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def sanitize_url(url: str, secret_values: list[str]) -> str:
    sanitized = url
    for value in secret_values:
        if value:
            sanitized = sanitized.replace(value, "REDACTED")
    return sanitized


def request_json(
    *,
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    secret_values: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        redacted_url = sanitize_url(url, secret_values or [])
        raise RuntimeError(f"HTTP {exc.code} for {redacted_url}: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        redacted_url = sanitize_url(url, secret_values or [])
        raise RuntimeError(f"Request failed for {redacted_url}: {exc.reason}") from exc


def build_url(base: str, path: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{base}{path}?{query}" if query else f"{base}{path}"


def jquants_daily_quotes(*, api_key: str, code: str, date: str, timeout: int) -> dict[str, Any]:
    params = {"code": code, "date": date}
    url = build_url(JQUANTS_BASE_URL, "/equities/bars/daily", params)
    status, payload = request_json(
        url=url,
        headers={"x-api-key": api_key},
        timeout=timeout,
        secret_values=[api_key],
    )
    return {
        "schema_version": "api_smoke_result_v1",
        "provider": "jquants",
        "endpoint": "/equities/bars/daily",
        "requested_at": now_jst(),
        "status_code": status,
        "request": {
            "url": sanitize_url(url, [api_key]),
            "code": code,
            "date": date,
            "auth": "x-api-key",
        },
        "response": payload,
        "summary": summarize_jquants_payload(payload),
    }


def summarize_jquants_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    if isinstance(payload.get("daily_quotes"), list):
        rows = payload["daily_quotes"]
    elif isinstance(payload.get("bars"), list):
        rows = payload["bars"]
    elif isinstance(payload.get("data"), list):
        rows = payload["data"]
    return {
        "top_level_keys": sorted(payload.keys()),
        "row_count": len(rows),
        "first_row_keys": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
    }


def edinet_documents(*, api_key: str, date: str, doc_type: str, timeout: int) -> dict[str, Any]:
    params = {
        "date": date,
        "type": doc_type,
        "Subscription-Key": api_key,
    }
    url = build_url(EDINET_BASE_URL, "/documents.json", params)
    status, payload = request_json(url=url, timeout=timeout, secret_values=[api_key])
    redacted_url = sanitize_url(url, [api_key])
    return {
        "schema_version": "api_smoke_result_v1",
        "provider": "edinet",
        "endpoint": "/documents.json",
        "requested_at": now_jst(),
        "status_code": status,
        "request": {
            "url": redacted_url,
            "date": date,
            "type": doc_type,
            "auth": "Subscription-Key query parameter",
        },
        "response": payload,
        "summary": summarize_edinet_payload(payload),
    }


def summarize_edinet_payload(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    rows = results if isinstance(results, list) else []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "top_level_keys": sorted(payload.keys()),
        "metadata_keys": sorted(metadata.keys()),
        "result_count": len(rows),
        "first_result_keys": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
    }


def secret_presence() -> dict[str, bool]:
    return {
        "JQUANTS_API_KEY": bool(os.environ.get("JQUANTS_API_KEY")),
        "EDINET_API_KEY": bool(os.environ.get("EDINET_API_KEY")),
    }


def assert_no_secret_leak(path: Path, secrets: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    leaked = [name for name in secrets if name and name in text]
    if leaked:
        raise RuntimeError(f"{path}: secret value leaked into saved output")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test J-Quants and EDINET API connectivity.")
    parser.add_argument("--provider", choices=["all", "jquants", "edinet"], default="all")
    parser.add_argument("--env-file", type=Path, help="Env file containing JQUANTS_API_KEY and/or EDINET_API_KEY.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data/raw/api_smoke")
    parser.add_argument("--date", default="2025-03-28", help="Date used for both providers unless overridden.")
    parser.add_argument("--jquants-code", default="86970", help="J-Quants V2 issue code. Default is JPX 8697 as 86970.")
    parser.add_argument("--jquants-date", help="YYYYMMDD date for J-Quants. Defaults to --date without hyphens.")
    parser.add_argument("--edinet-date", help="YYYY-MM-DD date for EDINET. Defaults to --date.")
    parser.add_argument("--edinet-type", default="2", help="EDINET document list type. 2 returns metadata list.")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    env_file = args.env_file if args.env_file else configured_env_file()
    loaded_keys = load_env_file(env_file)
    providers = ["jquants", "edinet"] if args.provider == "all" else [args.provider]
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    run_id = datetime.now(JST).strftime("%Y%m%dT%H%M%S")
    outputs: dict[str, str] = {}
    errors: dict[str, str] = {}

    jquants_key = os.environ.get("JQUANTS_API_KEY", "")
    edinet_key = os.environ.get("EDINET_API_KEY", "")
    secrets = [jquants_key, edinet_key]

    print(f"env_file={env_file}")
    print(f"loaded_env_keys={sorted(key for key in loaded_keys if key in {'JQUANTS_API_KEY', 'EDINET_API_KEY'})}")
    for key, present in secret_presence().items():
        print(f"{key}_present={present}")

    if "jquants" in providers:
        if not jquants_key:
            errors["jquants"] = "JQUANTS_API_KEY is not set"
        else:
            try:
                jquants_date = args.jquants_date or args.date.replace("-", "")
                payload = jquants_daily_quotes(
                    api_key=jquants_key,
                    code=args.jquants_code,
                    date=jquants_date,
                    timeout=args.timeout,
                )
                path = out_dir / "jquants" / run_id / f"daily_equities_bars_{args.jquants_code}_{jquants_date}.json"
                write_json(path, payload)
                assert_no_secret_leak(path, secrets)
                outputs["jquants"] = str(path)
            except Exception as exc:  # pragma: no cover - live API smoke.
                errors["jquants"] = str(exc)

    if "edinet" in providers:
        if not edinet_key:
            errors["edinet"] = "EDINET_API_KEY is not set"
        else:
            try:
                edinet_date = args.edinet_date or args.date
                payload = edinet_documents(
                    api_key=edinet_key,
                    date=edinet_date,
                    doc_type=args.edinet_type,
                    timeout=args.timeout,
                )
                path = out_dir / "edinet" / run_id / f"documents_{edinet_date}_type{args.edinet_type}.json"
                write_json(path, payload)
                assert_no_secret_leak(path, secrets)
                outputs["edinet"] = str(path)
            except Exception as exc:  # pragma: no cover - live API smoke.
                errors["edinet"] = str(exc)

    print("outputs=" + json.dumps(outputs, ensure_ascii=False, sort_keys=True))
    if errors:
        print("errors=" + json.dumps(errors, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
