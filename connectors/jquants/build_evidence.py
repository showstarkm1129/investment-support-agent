#!/usr/bin/env python3
"""Build Evidence JSON from normalized J-Quants daily quotes."""

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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def compact_date(value: str) -> str:
    return value.replace("-", "")


def direction_hint(record: dict[str, Any]) -> str:
    close = record.get("close")
    open_price = record.get("open")
    if isinstance(close, (int, float)) and isinstance(open_price, (int, float)):
        if close > open_price:
            return "upside"
        if close < open_price:
            return "downside"
    return "neutral"


def metrics_from_record(record: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover_value",
        "adjustment_factor",
        "adjusted_close",
    ]
    return {key: record.get(key) for key in keys if key in record}


def evidence_from_normalized(
    normalized: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if normalized.get("schema_version") != "jquants_normalized_daily_quotes_v1":
        raise ValueError("normalized artifact must have schema_version jquants_normalized_daily_quotes_v1")
    records = normalized.get("records")
    if not isinstance(records, list):
        raise ValueError("normalized artifact records must be a list")

    collected = collected_at or now_jst()
    evidence = []
    target_id = str(normalized.get("target_id") or "")
    date = str(normalized.get("date") or collected[:10])
    code = str(normalized.get("code") or stock_code)
    for index, record in enumerate([item for item in records if isinstance(item, dict)], start=1):
        title = f"J-Quants日次価格: {code} {date}"
        close = record.get("close")
        volume = record.get("volume")
        turnover = record.get("turnover_value")
        summary_parts = [f"{date}の{code}日次価格データをJ-Quantsから取得。"]
        if close is not None:
            summary_parts.append(f"終値は{close}。")
        if volume is not None:
            summary_parts.append(f"出来高は{volume}。")
        if turnover is not None:
            summary_parts.append(f"売買代金は{turnover}。")
        evidence.append(
            {
                "schema_version": "evidence_v1",
                "evidence_id": f"E{compact_date(date)}-{index:03d}",
                "identity": {
                    "target_id": target_id,
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "collected_at": collected,
                    "published_at": f"{date}T15:30:00+09:00",
                },
                "source": {
                    "source_type": "price_volume",
                    "source_name": "J-Quants API V2",
                    "source_url": null_url(),
                    "source_reliability": "A",
                    "save_policy": "structured_data",
                },
                "content": {
                    "title": title,
                    "summary": " ".join(summary_parts),
                    "excerpt": None,
                    "metrics": metrics_from_record(record),
                },
                "evaluation": {
                    "directness": "high",
                    "freshness": "high",
                    "impact_level": "low",
                    "direction_hint": direction_hint(record),
                    "related_topics": ["株価", "出来高", "売買代金"],
                    "hypothesis_impact": "価格・出来高の基礎データであり、単独では投資仮説を強く更新しない。",
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


def null_url() -> None:
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Evidence JSON from normalized J-Quants daily quotes.")
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    args = parser.parse_args()

    normalized_path = args.normalized if args.normalized.is_absolute() else ROOT / args.normalized
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    normalized = load_json(normalized_path)
    evidence = evidence_from_normalized(
        normalized,
        stock_code=args.stock_code,
        company_name=args.company_name,
    )
    write_json(out_path, evidence)
    print(f"evidence_path={out_path}")
    print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
