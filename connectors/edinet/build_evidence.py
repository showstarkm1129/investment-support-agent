#!/usr/bin/env python3
"""Build Evidence JSON from EDINET document metadata."""

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


def rows_from_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    rows = response.get("results") if isinstance(response, dict) else []
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def document_datetime(row: dict[str, Any], fallback_date: str) -> str:
    raw = str(row.get("submitDateTime") or "").strip()
    if raw:
        normalized = raw.replace("/", "-").replace(" ", "T")
        if len(normalized) == 16:
            normalized += ":00"
        if normalized.endswith("+09:00"):
            return normalized
        return f"{normalized}+09:00"
    return f"{fallback_date}T00:00:00+09:00"


def document_title(row: dict[str, Any]) -> str:
    description = str(row.get("docDescription") or "").strip()
    filer = str(row.get("filerName") or "").strip()
    if description and filer:
        return f"EDINET開示: {filer} / {description}"
    return description or filer or "EDINET開示"


def matches_target(row: dict[str, Any], *, sec_code: str | None, filer_name_contains: str | None) -> bool:
    if sec_code:
        row_sec = str(row.get("secCode") or "")
        if row_sec == sec_code or row_sec.rstrip("0") == sec_code.rstrip("0"):
            return True
    if filer_name_contains:
        filer = str(row.get("filerName") or "")
        if filer_name_contains in filer:
            return True
    return not sec_code and not filer_name_contains


def evidence_from_raw(
    raw: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    sec_code: str | None = None,
    filer_name_contains: str | None = None,
    max_items: int = 20,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if raw.get("schema_version") != "edinet_raw_documents_v1":
        raise ValueError("raw artifact must have schema_version edinet_raw_documents_v1")
    collected = collected_at or now_jst()
    target_id = str(raw.get("target_id") or "")
    date = str(raw.get("date") or collected[:10])
    rows = [
        row
        for row in rows_from_raw(raw)
        if matches_target(row, sec_code=sec_code, filer_name_contains=filer_name_contains)
    ][:max_items]
    if not rows:
        total_rows = len(rows_from_raw(raw))
        return [
            {
                "schema_version": "evidence_v1",
                "evidence_id": f"E{compact_date(date)}-101",
                "identity": {
                    "target_id": target_id,
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "collected_at": collected,
                    "published_at": f"{date}T23:59:59+09:00",
                },
                "source": {
                    "source_type": "disclosure_edinet",
                    "source_name": "EDINET API V2",
                    "source_url": None,
                    "source_reliability": "A",
                    "save_policy": "structured_data",
                },
                "content": {
                    "title": f"EDINET開示確認: {company_name} {date}",
                    "summary": f"{date}のEDINET提出書類一覧を確認したが、{company_name}に一致する開示メタデータは見つからなかった。",
                    "excerpt": None,
                    "metrics": {
                        "matched_document_count": 0,
                        "total_document_count": total_rows,
                        "sec_code_filter": sec_code,
                        "filer_name_filter": filer_name_contains,
                    },
                },
                "evaluation": {
                    "directness": "medium",
                    "freshness": "high",
                    "impact_level": "low",
                    "direction_hint": "neutral",
                    "related_topics": ["EDINET", "開示なし", "公的開示"],
                    "hypothesis_impact": "対象会社の該当開示が見つからないことを示す確認情報であり、単独では投資仮説を強く更新しない。",
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
    evidence = []
    for index, row in enumerate(rows, start=101):
        doc_id = str(row.get("docID") or "")
        description = str(row.get("docDescription") or "")
        filer = str(row.get("filerName") or company_name)
        summary = f"{date}にEDINETで{filer}の開示メタデータを確認。"
        if description:
            summary += f" 書類概要: {description}。"
        evidence.append(
            {
                "schema_version": "evidence_v1",
                "evidence_id": f"E{compact_date(date)}-{index:03d}",
                "identity": {
                    "target_id": target_id,
                    "stock_code": stock_code,
                    "company_name": company_name,
                    "collected_at": collected,
                    "published_at": document_datetime(row, date),
                },
                "source": {
                    "source_type": "disclosure_edinet",
                    "source_name": "EDINET API V2",
                    "source_url": f"https://disclosure2.edinet-fsa.go.jp/WEEK0010.aspx?docID={doc_id}" if doc_id else None,
                    "source_reliability": "A",
                    "save_policy": "structured_data",
                },
                "content": {
                    "title": document_title(row),
                    "summary": summary,
                    "excerpt": None,
                    "metrics": {
                        "doc_id": doc_id,
                        "edinet_code": row.get("edinetCode"),
                        "sec_code": row.get("secCode"),
                        "doc_type_code": row.get("docTypeCode"),
                        "form_code": row.get("formCode"),
                        "ordinance_code": row.get("ordinanceCode"),
                    },
                },
                "evaluation": {
                    "directness": "high",
                    "freshness": "high",
                    "impact_level": "medium",
                    "direction_hint": "neutral",
                    "related_topics": ["EDINET", "開示", "公的開示"],
                    "hypothesis_impact": "公的開示の存在確認であり、内容精査前のため方向性は中立として扱う。",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Evidence JSON from EDINET raw document metadata.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--sec-code")
    parser.add_argument("--filer-name-contains")
    parser.add_argument("--max-items", type=int, default=20)
    args = parser.parse_args()

    raw_path = args.raw if args.raw.is_absolute() else ROOT / args.raw
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    raw = load_json(raw_path)
    evidence = evidence_from_raw(
        raw,
        stock_code=args.stock_code,
        company_name=args.company_name,
        sec_code=args.sec_code,
        filer_name_contains=args.filer_name_contains,
        max_items=args.max_items,
    )
    write_json(out_path, evidence)
    print(f"evidence_path={out_path}")
    print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
