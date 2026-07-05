#!/usr/bin/env python3
"""Build multi-day normalized J-Quants history from raw daily quote artifacts."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from normalize_daily_quotes import normalize_raw


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (str(record.get("date") or ""), str(record.get("code") or ""))
        if key[0]:
            by_key[key] = record
    return sorted(by_key.values(), key=lambda item: (str(item.get("date") or ""), str(item.get("code") or "")))


def build_history(raw_paths: list[Path]) -> dict[str, Any]:
    if not raw_paths:
        raise ValueError("at least one raw artifact is required")
    normalized_items = []
    records: list[dict[str, Any]] = []
    for raw_path in raw_paths:
        raw = load_json(raw_path)
        normalized = normalize_raw(raw, raw_path=raw_path)
        normalized_items.append(normalized)
        records.extend(item for item in normalized.get("records", []) if isinstance(item, dict))
    records = unique_records(records)
    latest_date = str(records[-1].get("date") or normalized_items[-1].get("date") or "") if records else str(normalized_items[-1].get("date") or "")
    return {
        "schema_version": "jquants_normalized_daily_quotes_v1",
        "provider": "jquants",
        "normalized_at": normalized_items[-1].get("normalized_at"),
        "target_id": str(normalized_items[-1].get("target_id") or ""),
        "code": str(normalized_items[-1].get("code") or ""),
        "date": latest_date,
        "source_raw_path": ",".join(str(path) for path in raw_paths),
        "record_count": len(records),
        "records": records,
        "quality": {
            "has_records": bool(records),
            "source_status_code": normalized_items[-1].get("quality", {}).get("source_status_code"),
            "source_row_count": sum(int(item.get("quality", {}).get("source_row_count") or 0) for item in normalized_items),
            "source_file_count": len(raw_paths),
        },
    }


def expand_inputs(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        matches = sorted(glob.glob(value))
        if matches:
            paths.extend(Path(item) for item in matches)
        else:
            paths.append(Path(value))
    resolved = []
    for path in paths:
        resolved.append(path if path.is_absolute() else ROOT / path)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized J-Quants history from raw artifacts.")
    parser.add_argument("--raw", action="append", default=[], help="Raw artifact path or glob. Can be passed multiple times.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    raw_paths = expand_inputs(args.raw)
    history = build_history(raw_paths)
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    write_json(out_path, history)
    print(f"history_path={out_path}")
    print(f"record_count={history['record_count']}")
    print(f"source_file_count={history['quality']['source_file_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
