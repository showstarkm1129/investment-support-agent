#!/usr/bin/env python3
"""Build derived price/volume indicators and Evidence from normalized J-Quants data."""

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


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 4)


def average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def trailing_average(records: list[dict[str, Any]], key: str, window: int) -> float | None:
    values = [number(item.get(key)) for item in records[-window:]]
    clean = [item for item in values if item is not None]
    if len(clean) < window:
        return None
    return average(clean)


def latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    clean = [item for item in records if isinstance(item, dict)]
    if not clean:
        return None
    return sorted(clean, key=lambda item: str(item.get("date") or ""))[-1]


def previous_record(records: list[dict[str, Any]], latest: dict[str, Any]) -> dict[str, Any] | None:
    clean = sorted([item for item in records if isinstance(item, dict)], key=lambda item: str(item.get("date") or ""))
    if len(clean) < 2:
        return None
    if clean[-1] is latest:
        return clean[-2]
    return clean[-2]


def indicator_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    latest = latest_record(records)
    if latest is None:
        return {}
    previous = previous_record(records, latest)
    open_price = number(latest.get("open"))
    high = number(latest.get("high"))
    low = number(latest.get("low"))
    close = number(latest.get("close"))
    volume = number(latest.get("volume"))
    previous_close = number(previous.get("close")) if previous else None
    ma_5 = trailing_average(records, "close", 5)
    ma_20 = trailing_average(records, "close", 20)
    volume_ma_5 = trailing_average(records, "volume", 5)
    intraday_range = None
    if high is not None and low is not None and open_price not in (None, 0):
        intraday_range = round((high - low) / open_price * 100, 4)
    close_position = None
    if high is not None and low is not None and close is not None and high != low:
        close_position = round((close - low) / (high - low) * 100, 4)
    return {
        "date": latest.get("date"),
        "code": latest.get("code"),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "previous_close": previous_close,
        "close_to_open_pct": pct(close - open_price if close is not None and open_price is not None else None, open_price),
        "change_pct": pct(close - previous_close if close is not None and previous_close is not None else None, previous_close),
        "intraday_range_pct": intraday_range,
        "close_position_pct": close_position,
        "ma_5": ma_5,
        "ma_20": ma_20,
        "close_vs_ma_5_pct": pct(close - ma_5 if close is not None and ma_5 is not None else None, ma_5),
        "close_vs_ma_20_pct": pct(close - ma_20 if close is not None and ma_20 is not None else None, ma_20),
        "volume_ma_5": volume_ma_5,
        "volume_ratio_5d": round(volume / volume_ma_5, 4) if volume is not None and volume_ma_5 not in (None, 0) else None,
    }


def direction_hint(metrics: dict[str, Any]) -> str:
    for key in ["change_pct", "close_to_open_pct", "close_vs_ma_5_pct"]:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            if value > 0:
                return "upside"
            if value < 0:
                return "downside"
    return "neutral"


def indicators_from_normalized(normalized: dict[str, Any]) -> dict[str, Any]:
    if normalized.get("schema_version") != "jquants_normalized_daily_quotes_v1":
        raise ValueError("normalized artifact must have schema_version jquants_normalized_daily_quotes_v1")
    records = normalized.get("records")
    if not isinstance(records, list):
        raise ValueError("normalized artifact records must be a list")
    metrics = indicator_metrics(records)
    return {
        "schema_version": "jquants_derived_indicators_v1",
        "provider": "jquants",
        "derived_at": now_jst(),
        "target_id": str(normalized.get("target_id") or ""),
        "code": str(normalized.get("code") or metrics.get("code") or ""),
        "date": str(metrics.get("date") or normalized.get("date") or ""),
        "source_normalized_path": normalized.get("source_raw_path"),
        "record_count": len(records),
        "metrics": metrics,
        "quality": {
            "has_latest_record": bool(metrics),
            "has_previous_close": metrics.get("previous_close") is not None,
            "has_ma_5": metrics.get("ma_5") is not None,
            "has_ma_20": metrics.get("ma_20") is not None,
        },
    }


def compact_date(value: str) -> str:
    return value.replace("-", "")


def evidence_from_indicators(
    indicators: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if indicators.get("schema_version") != "jquants_derived_indicators_v1":
        raise ValueError("indicator artifact must have schema_version jquants_derived_indicators_v1")
    metrics = indicators.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return []
    metrics = {key: value for key, value in metrics.items() if value is not None}
    if not metrics:
        return []
    collected = collected_at or now_jst()
    target_id = str(indicators.get("target_id") or "")
    date = str(indicators.get("date") or collected[:10])
    code = str(indicators.get("code") or stock_code)
    summary_parts = [f"{date}の{code}についてJ-Quants価格データから派生指標を算出。"]
    for key, label in [
        ("change_pct", "前日比"),
        ("close_to_open_pct", "始値比"),
        ("intraday_range_pct", "日中レンジ"),
        ("volume_ratio_5d", "5日平均比出来高"),
    ]:
        value = metrics.get(key)
        if value is not None:
            summary_parts.append(f"{label}は{value}。")
    return [
        {
            "schema_version": "evidence_v1",
            "evidence_id": f"E{compact_date(date)}-051",
            "identity": {
                "target_id": target_id,
                "stock_code": stock_code,
                "company_name": company_name,
                "collected_at": collected,
                "published_at": f"{date}T15:30:00+09:00",
            },
            "source": {
                "source_type": "price_volume",
                "source_name": "J-Quants derived indicators",
                "source_url": None,
                "source_reliability": "A",
                "save_policy": "structured_data",
            },
            "content": {
                "title": f"J-Quants派生指標: {code} {date}",
                "summary": " ".join(summary_parts),
                "excerpt": None,
                "metrics": metrics,
            },
            "evaluation": {
                "directness": "medium",
                "freshness": "high",
                "impact_level": "medium",
                "direction_hint": direction_hint(metrics),
                "related_topics": ["株価", "出来高", "移動平均", "派生指標"],
                "hypothesis_impact": "価格・出来高の派生指標であり、材料の価格反応や短期需給の確認に使う。",
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
    parser = argparse.ArgumentParser(description="Build derived J-Quants indicators and optional Evidence.")
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--stock-code")
    parser.add_argument("--company-name")
    args = parser.parse_args()

    normalized_path = args.normalized if args.normalized.is_absolute() else ROOT / args.normalized
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    normalized = load_json(normalized_path)
    indicators = indicators_from_normalized(normalized)
    write_json(out_path, indicators)
    print(f"indicators_path={out_path}")
    if args.evidence_out:
        if not args.stock_code or not args.company_name:
            raise ValueError("--stock-code and --company-name are required with --evidence-out")
        evidence_path = args.evidence_out if args.evidence_out.is_absolute() else ROOT / args.evidence_out
        evidence = evidence_from_indicators(indicators, stock_code=args.stock_code, company_name=args.company_name)
        write_json(evidence_path, evidence)
        print(f"evidence_path={evidence_path}")
        print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
