#!/usr/bin/env python3
"""Build relative benchmark/sector comparison Evidence from normalized J-Quants data."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_indicators import indicator_metrics


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


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug[:80] or "benchmark"


def require_normalized(normalized: dict[str, Any]) -> None:
    if normalized.get("schema_version") != "jquants_normalized_daily_quotes_v1":
        raise ValueError("normalized artifact must have schema_version jquants_normalized_daily_quotes_v1")
    if not isinstance(normalized.get("records"), list):
        raise ValueError("normalized artifact records must be a list")


def pick_relative_key(target_metrics: dict[str, Any], benchmark_metrics: dict[str, Any]) -> str | None:
    for key in ["change_pct", "close_to_open_pct", "close_vs_ma_5_pct"]:
        if isinstance(target_metrics.get(key), (int, float)) and isinstance(benchmark_metrics.get(key), (int, float)):
            return key
    return None


def comparison_direction(relative_pct: float | None) -> str:
    if relative_pct is None:
        return "neutral"
    if relative_pct > 0:
        return "upside"
    if relative_pct < 0:
        return "downside"
    return "neutral"


def comparison_entry(target_metrics: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    normalized = benchmark["normalized"]
    benchmark_metrics = indicator_metrics(normalized["records"])
    relative_key = pick_relative_key(target_metrics, benchmark_metrics)
    target_value = target_metrics.get(relative_key) if relative_key else None
    benchmark_value = benchmark_metrics.get(relative_key) if relative_key else None
    relative_pct = None
    if isinstance(target_value, (int, float)) and isinstance(benchmark_value, (int, float)):
        relative_pct = round(target_value - benchmark_value, 4)
    return {
        "label": benchmark["label"],
        "code": str(normalized.get("code") or benchmark_metrics.get("code") or ""),
        "date": str(benchmark_metrics.get("date") or normalized.get("date") or ""),
        "comparison_metric": relative_key,
        "target_value_pct": target_value,
        "benchmark_value_pct": benchmark_value,
        "relative_pct": relative_pct,
        "target_close": target_metrics.get("close"),
        "benchmark_close": benchmark_metrics.get("close"),
        "target_volume_ratio_5d": target_metrics.get("volume_ratio_5d"),
        "benchmark_volume_ratio_5d": benchmark_metrics.get("volume_ratio_5d"),
    }


def relative_comparison_from_normalized(
    *,
    target_normalized: dict[str, Any],
    benchmarks: list[dict[str, Any]],
) -> dict[str, Any]:
    require_normalized(target_normalized)
    if not benchmarks:
        raise ValueError("at least one benchmark is required")
    target_metrics = indicator_metrics(target_normalized["records"])
    if not target_metrics:
        raise ValueError("target normalized artifact has no usable records")
    entries = []
    for benchmark in benchmarks:
        normalized = benchmark.get("normalized")
        if not isinstance(normalized, dict):
            raise ValueError("benchmark normalized artifact must be a dict")
        require_normalized(normalized)
        entries.append(comparison_entry(target_metrics, benchmark))
    date = str(target_metrics.get("date") or target_normalized.get("date") or "")
    return {
        "schema_version": "jquants_relative_comparison_v1",
        "provider": "jquants",
        "derived_at": now_jst(),
        "target_id": str(target_normalized.get("target_id") or ""),
        "code": str(target_normalized.get("code") or target_metrics.get("code") or ""),
        "date": date,
        "source_normalized_path": target_normalized.get("source_raw_path"),
        "target_metrics": target_metrics,
        "comparisons": entries,
        "quality": {
            "benchmark_count": len(entries),
            "comparable_count": sum(1 for item in entries if item.get("relative_pct") is not None),
            "has_relative_signal": any(item.get("relative_pct") is not None for item in entries),
        },
    }


def clean_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metrics.items() if value is not None}


def evidence_from_relative_comparison(
    comparison: dict[str, Any],
    *,
    stock_code: str,
    company_name: str,
    collected_at: str | None = None,
) -> list[dict[str, Any]]:
    if comparison.get("schema_version") != "jquants_relative_comparison_v1":
        raise ValueError("comparison artifact must have schema_version jquants_relative_comparison_v1")
    entries = comparison.get("comparisons")
    if not isinstance(entries, list) or not entries:
        return []
    collected = collected_at or now_jst()
    target_id = str(comparison.get("target_id") or "")
    date = str(comparison.get("date") or collected[:10])
    code = str(comparison.get("code") or stock_code)
    metrics: dict[str, Any] = {
        "target_code": code,
        "benchmark_count": len(entries),
    }
    summary_parts = [f"{date}の{code}を比較対象と相対比較。"]
    relative_values = []
    for index, entry in enumerate(entries, start=1):
        label = str(entry.get("label") or f"benchmark_{index}")
        metric_key = entry.get("comparison_metric")
        relative = entry.get("relative_pct")
        prefix = safe_slug(label)
        for key, value in clean_metrics(entry).items():
            metrics[f"{prefix}_{key}"] = value
        if isinstance(relative, (int, float)):
            relative_values.append(relative)
            summary_parts.append(f"{label}比の{metric_key}差は{relative}pt。")
        else:
            summary_parts.append(f"{label}とは比較可能な変化率が不足。")
    average_relative = round(sum(relative_values) / len(relative_values), 4) if relative_values else None
    if average_relative is not None:
        metrics["average_relative_pct"] = average_relative
    return [
        {
            "schema_version": "evidence_v1",
            "evidence_id": f"E{compact_date(date)}-061",
            "identity": {
                "target_id": target_id,
                "stock_code": stock_code,
                "company_name": company_name,
                "collected_at": collected,
                "published_at": f"{date}T15:30:00+09:00",
            },
            "source": {
                "source_type": "market_supply",
                "source_name": "J-Quants relative benchmark comparison",
                "source_url": None,
                "source_reliability": "A",
                "save_policy": "structured_data",
            },
            "content": {
                "title": f"J-Quants相対比較: {code} {date}",
                "summary": " ".join(summary_parts),
                "excerpt": None,
                "metrics": metrics,
            },
            "evaluation": {
                "directness": "medium",
                "freshness": "high",
                "impact_level": "medium",
                "direction_hint": comparison_direction(average_relative),
                "related_topics": ["相対比較", "指数比較", "セクター比較", "地合い"],
                "hypothesis_impact": "対象銘柄の値動きが比較対象に対して強いか弱いかを確認し、個別要因と市場要因の切り分けに使う。",
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


def parse_benchmark(value: str) -> tuple[str, Path]:
    if "=" not in value:
        path = Path(value)
        return path.stem, path
    label, path = value.split("=", 1)
    if not label.strip() or not path.strip():
        raise ValueError("--benchmark must be LABEL=normalized.json")
    return label.strip(), Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build relative benchmark comparison from normalized J-Quants artifacts.")
    parser.add_argument("--target-normalized", type=Path, required=True)
    parser.add_argument("--benchmark", action="append", default=[], help="Benchmark as LABEL=normalized.json. Can be repeated.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--stock-code")
    parser.add_argument("--company-name")
    args = parser.parse_args()

    target_path = args.target_normalized if args.target_normalized.is_absolute() else ROOT / args.target_normalized
    target_normalized = load_json(target_path)
    benchmarks = []
    for item in args.benchmark:
        label, path = parse_benchmark(item)
        normalized_path = path if path.is_absolute() else ROOT / path
        benchmarks.append({"label": label, "normalized": load_json(normalized_path)})
    comparison = relative_comparison_from_normalized(target_normalized=target_normalized, benchmarks=benchmarks)
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    write_json(out_path, comparison)
    print(f"comparison_path={out_path}")
    print(f"benchmark_count={comparison['quality']['benchmark_count']}")
    if args.evidence_out:
        if not args.stock_code or not args.company_name:
            raise ValueError("--stock-code and --company-name are required with --evidence-out")
        evidence_path = args.evidence_out if args.evidence_out.is_absolute() else ROOT / args.evidence_out
        evidence = evidence_from_relative_comparison(comparison, stock_code=args.stock_code, company_name=args.company_name)
        write_json(evidence_path, evidence)
        print(f"evidence_path={evidence_path}")
        print(f"evidence_count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
