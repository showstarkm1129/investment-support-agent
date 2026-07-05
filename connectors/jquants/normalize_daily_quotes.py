#!/usr/bin/env python3
"""Normalize J-Quants raw daily quotes into a compact connector artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JST = timezone(timedelta(hours=9))


FIELD_MAP = {
    "Date": "date",
    "Code": "code",
    "O": "open",
    "H": "high",
    "L": "low",
    "C": "close",
    "Vo": "volume",
    "Va": "turnover_value",
    "AdjO": "adjusted_open",
    "AdjH": "adjusted_high",
    "AdjL": "adjusted_low",
    "AdjC": "adjusted_close",
    "AdjVo": "adjusted_volume",
    "AdjFactor": "adjustment_factor",
    "UL": "upper_limit",
    "LL": "lower_limit",
}


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def rows_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    response = raw.get("response") if isinstance(raw.get("response"), dict) else raw
    if not isinstance(response, dict):
        return []
    for key in ["data", "daily_quotes", "bars"]:
        rows = response.get(key)
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def normalize_value(value: Any) -> Any:
    if value == "":
        return None
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for source_key, target_key in FIELD_MAP.items():
        if source_key in row:
            normalized[target_key] = normalize_value(row[source_key])
    for key in ["date", "code"]:
        normalized.setdefault(key, "")
    return normalized


def normalize_raw(raw: dict[str, Any], *, raw_path: Path) -> dict[str, Any]:
    if raw.get("schema_version") != "jquants_raw_daily_quotes_v1":
        raise ValueError("raw artifact must have schema_version jquants_raw_daily_quotes_v1")
    rows = rows_from_raw(raw)
    records = [normalize_row(row) for row in rows]
    target_id = str(raw.get("target_id") or "")
    date = str(raw.get("date") or "")
    code = str(raw.get("code") or "")
    return {
        "schema_version": "jquants_normalized_daily_quotes_v1",
        "provider": "jquants",
        "normalized_at": now_jst(),
        "target_id": target_id,
        "code": code,
        "date": date,
        "source_raw_path": str(raw_path),
        "record_count": len(records),
        "records": records,
        "quality": {
            "has_records": bool(records),
            "source_status_code": raw.get("status_code"),
            "source_row_count": raw.get("summary", {}).get("row_count") if isinstance(raw.get("summary"), dict) else None,
        },
    }


def output_path(*, out_root: Path, target_id: str, date: str) -> Path:
    return out_root / date / f"{target_id}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a J-Quants raw daily quotes artifact.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, default=ROOT / "data/normalized/jquants")
    args = parser.parse_args()

    raw_path = args.raw if args.raw.is_absolute() else ROOT / args.raw
    raw = load_json(raw_path)
    normalized = normalize_raw(raw, raw_path=raw_path)
    out_root = args.out_root if args.out_root.is_absolute() else ROOT / args.out_root
    path = output_path(out_root=out_root, target_id=normalized["target_id"], date=normalized["date"])
    write_json(path, normalized)
    print(f"normalized_path={path}")
    print(f"record_count={normalized['record_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
