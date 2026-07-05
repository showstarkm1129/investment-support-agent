#!/usr/bin/env python3
"""Build Evidence JSON from official IR page metadata."""

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


def evidence_from_raw(
    raw: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    date: str,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if raw.get("schema_version") != "ir_raw_page_v1":
        raise ValueError("raw artifact must have schema_version ir_raw_page_v1")
    collected = collected_at or now_jst()
    target_id = str(raw.get("target_id") or "")
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    title = str(metadata.get("title") or f"{company_name} IR")
    description = metadata.get("description")
    snippet = metadata.get("snippet")
    url = raw.get("url") if isinstance(raw.get("url"), str) else None
    summary_parts = [f"{date}に{company_name}の公式IRページを確認。", f"タイトル: {title}。"]
    if isinstance(description, str) and description:
        summary_parts.append(f"概要: {description[:220]}")
    return [
        {
            "schema_version": "evidence_v1",
            "evidence_id": f"E{compact_date(date)}-301",
            "identity": {
                "target_id": target_id,
                "stock_code": stock_code,
                "company_name": company_name,
                "collected_at": collected,
                "published_at": f"{date}T00:00:00+09:00",
            },
            "source": {
                "source_type": "ir",
                "source_name": "Official IR",
                "source_url": url,
                "source_reliability": "A",
                "save_policy": "summary_and_short_excerpt",
            },
            "content": {
                "title": title,
                "summary": " ".join(summary_parts),
                "excerpt": snippet[:500] if isinstance(snippet, str) and snippet else None,
                "metrics": {
                    "url": url,
                    "content_type": raw.get("content_type"),
                    "status_code": raw.get("status_code"),
                },
            },
            "evaluation": {
                "directness": "high",
                "freshness": "medium",
                "impact_level": "medium",
                "direction_hint": "unknown",
                "related_topics": ["IR", "公式情報", "企業開示"],
                "hypothesis_impact": "公式IR情報源の確認であり、個別資料の内容精査前のため方向性はunknownとして扱う。",
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
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Evidence JSON from official IR raw metadata.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    raw_path = args.raw if args.raw.is_absolute() else ROOT / args.raw
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    raw = load_json(raw_path)
    evidence = evidence_from_raw(raw, stock_code=args.stock_code, company_name=args.company_name, date=args.date)
    write_json(out_path, evidence)
    print(f"evidence_path={out_path}")
    print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
