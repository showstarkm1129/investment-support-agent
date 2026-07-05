#!/usr/bin/env python3
"""Build deterministic AgentTeam readout JSON from Evidence.

This script is intentionally conservative. It does not pretend to be a full
AI analyst; it creates schema-valid agent and judge artifacts from existing
Evidence so the pipeline can be exercised end to end.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


JST = timezone(timedelta(hours=9))
ANALYSIS_AGENTS = ["bull", "bear", "contradiction", "pricing"]


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_ids(evidence: list[dict[str, Any]], direction: str | None = None, source_type: str | None = None) -> list[str]:
    ids = []
    for item in evidence:
        if direction is not None and item.get("evaluation", {}).get("direction_hint") != direction:
            continue
        if source_type is not None and item.get("source", {}).get("source_type") != source_type:
            continue
        ids.append(item["evidence_id"])
    return ids


def first_metric(evidence: list[dict[str, Any]], key: str) -> Any:
    for item in evidence:
        metrics = item.get("content", {}).get("metrics", {})
        if key in metrics:
            return metrics[key]
    return None


def price_move_summary(evidence: list[dict[str, Any]]) -> str:
    open_price = first_metric(evidence, "open")
    close_price = first_metric(evidence, "close")
    volume = first_metric(evidence, "volume")
    if open_price is None or close_price is None:
        return "価格データは取得済みだが、始値と終値の比較に必要な数値が不足している。"
    direction = "上回った" if close_price > open_price else "下回った" if close_price < open_price else "同水準だった"
    volume_text = f"出来高は{volume}。" if volume is not None else "出来高は未確認。"
    return f"終値{close_price}は始値{open_price}を{direction}。{volume_text}"


def direction_counts(evidence: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"upside": 0, "downside": 0, "contradiction": 0, "priced_in": 0, "neutral": 0, "unknown": 0}
    for item in evidence:
        direction = item.get("evaluation", {}).get("direction_hint", "unknown")
        counts[direction] = counts.get(direction, 0) + 1
    return counts


def weight_from_counts(counts: dict[str, int], has_price_volume: bool) -> dict[str, int]:
    raw = {
        "upside": counts.get("upside", 0) * 35,
        "downside": counts.get("downside", 0) * 35,
        "contradiction": counts.get("contradiction", 0) * 30,
        "priced_in": counts.get("priced_in", 0) * 30 + (15 if has_price_volume else 0),
    }
    if not any(raw.values()):
        raw["priced_in"] = 100

    total = sum(raw.values())
    weights = {key: int(round(value * 100 / total)) for key, value in raw.items()}
    diff = 100 - sum(weights.values())
    weights["priced_in"] += diff
    return weights


def balance_score(weights: dict[str, int]) -> int:
    return max(-100, min(100, weights["upside"] - weights["downside"] - weights["contradiction"] // 2))


def readout_label(score: int) -> str:
    if score >= 55:
        return "upside"
    if score >= 15:
        return "slightly_upside"
    if score <= -55:
        return "downside"
    if score <= -15:
        return "slightly_downside"
    return "neutral"


def information_label(weights: dict[str, int]) -> str:
    if weights["upside"] > weights["downside"] + 15:
        return "upside_evidence_leading"
    if weights["downside"] > weights["upside"] + 15:
        return "downside_evidence_leading"
    if weights["upside"] or weights["downside"]:
        return "mixed"
    return "insufficient_information"


def hypothesis_label(score: int) -> str:
    if score >= 55:
        return "supportive"
    if score >= 15:
        return "slightly_supportive"
    if score <= -55:
        return "negative"
    if score <= -15:
        return "slightly_negative"
    return "neutral"


def agent_output(
    *,
    agent_name: str,
    run_id: str,
    evidence_refs: list[str],
    conclusion: str,
    strength: int,
    key_points: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    stances = {
        "bull": "中期仮説を補強する事実を整理する",
        "bear": "中期仮説を弱める事実や短期リスクを整理する",
        "contradiction": "仮説に反する材料や矛盾を整理する",
        "pricing": "材料が価格に織り込まれている可能性を整理する",
    }
    confidence = "medium" if evidence_refs else "low"
    return {
        "schema_version": "agent_output_v1",
        "agent_name": agent_name,
        "run_id": run_id,
        "stance": stances[agent_name],
        "conclusion": conclusion,
        "claim_strength": max(0, min(100, strength)),
        "confidence": confidence,
        "evidence_ids": evidence_refs,
        "key_points": key_points,
        "limitations": limitations,
    }


def build_agent_outputs(evidence: list[dict[str, Any]], *, target_id: str, report_date: str, run_id: str) -> dict[str, Any]:
    upside_ids = evidence_ids(evidence, "upside")
    downside_ids = evidence_ids(evidence, "downside")
    contradiction_ids = evidence_ids(evidence, "contradiction")
    price_ids = evidence_ids(evidence, source_type="price_volume")
    move_summary = price_move_summary(evidence)

    outputs = [
        agent_output(
            agent_name="bull",
            run_id=f"{run_id}-BULL",
            evidence_refs=upside_ids,
            conclusion="上方向Evidenceがある場合は仮説補強候補として扱う。現時点では価格・出来高の一次データを中心に確認する。",
            strength=20 + len(upside_ids) * 25,
            key_points=[move_summary] if upside_ids else ["上方向を直接示すEvidenceはまだ少ない。"],
            limitations=["価格データ単独では事業要因や需給主体を特定できない。"],
        ),
        agent_output(
            agent_name="bear",
            run_id=f"{run_id}-BEAR",
            evidence_refs=downside_ids,
            conclusion="下方向Evidenceがある場合は短期リスクとして扱う。事業悪化の確認には追加情報が必要。",
            strength=20 + len(downside_ids) * 25,
            key_points=[move_summary] if downside_ids else ["下方向を直接示すEvidenceはまだ少ない。"],
            limitations=["価格下落が一時的な需給か、業績・材料変化かは未判定。"],
        ),
        agent_output(
            agent_name="contradiction",
            run_id=f"{run_id}-CONTRA",
            evidence_refs=contradiction_ids,
            conclusion="既存仮説を明確に壊すEvidenceは、現時点の価格データだけでは限定的。",
            strength=15 + len(contradiction_ids) * 20,
            key_points=["仮説反証には、開示・IR・ニュースなど価格以外のEvidence追加が必要。"],
            limitations=["反証探索は価格データだけでは不十分。"],
        ),
        agent_output(
            agent_name="pricing",
            run_id=f"{run_id}-PRICING",
            evidence_refs=price_ids,
            conclusion="価格・出来高Evidenceは織り込み状況を見る入口になるが、単独では過熱・割安を断定しない。",
            strength=25 + len(price_ids) * 15,
            key_points=[move_summary] if price_ids else ["価格・出来高Evidenceは未取得。"],
            limitations=["前日比、移動平均、信用残、同業比較が未確認。"],
        ),
    ]
    return {
        "schema_version": "agent_outputs_bundle_v1",
        "target_id": target_id,
        "report_date": report_date,
        "agent_outputs": outputs,
    }


def build_report_judge(
    evidence: list[dict[str, Any]],
    *,
    target_id: str,
    stock_code: str,
    company_name: str,
    market: str,
    themes: list[str],
    run_id: str,
    run_at: str,
) -> dict[str, Any]:
    counts = direction_counts(evidence)
    has_price_volume = bool(evidence_ids(evidence, source_type="price_volume"))
    weights = weight_from_counts(counts, has_price_volume)
    score = balance_score(weights)
    label = readout_label(score)
    info_label = information_label(weights)
    hypo_label = hypothesis_label(score)
    all_ids = [item["evidence_id"] for item in evidence]

    summary = f"Evidence {len(evidence)}件を確認。{price_move_summary(evidence)}"
    used_evidence = [
        {
            "evidence_id": item["evidence_id"],
            "role": item.get("evaluation", {}).get("direction_hint", "neutral"),
            "reason": item.get("content", {}).get("summary", "AgentTeam判断に使用したEvidence。"),
        }
        for item in evidence
    ]

    return {
        "schema_version": "report_readout_v1",
        "run_id": f"{run_id}-JUDGE",
        "agent_name": "report_judge",
        "run_at": run_at,
        "decision_stage": "draft",
        "target": {
            "target_id": target_id,
            "target_type": "stock",
            "stock_code": stock_code,
            "company_name": company_name,
            "market": market,
            "themes": themes,
        },
        "market_readout": {
            "label": label,
            "evidence_balance_score": score,
            "confidence": "medium" if evidence else "low",
            "summary": summary,
        },
        "information_status": {
            "label": info_label,
            "summary": "価格・出来高EvidenceをAgentTeam形式に整理した。追加情報で判断精度を上げる余地がある。",
        },
        "hypothesis_impact": {
            "label": hypo_label,
            "summary": "現段階では価格Evidence中心のため、仮説更新は暫定扱いにする。",
        },
        "uncertainty": {
            "level": "medium" if evidence else "high",
            "factors": [
                "J-Quants価格データ以外の材料が未統合",
                "ニュース、IR、EDINET、同業比較が未確認",
                "AI推論ではなく deterministic baseline による整理",
            ],
        },
        "evidence_weight": weights,
        "view_change_conditions": [
            {
                "condition": "同方向の価格・出来高Evidenceが複数営業日継続する",
                "effect": "現在の方向性判断の信頼度が上がる",
                "related_hypothesis": "短期需給・材料反応の継続性",
                "related_evidence_ids": all_ids,
            },
            {
                "condition": "IR、EDINET、ニュースで反対方向の材料が確認される",
                "effect": "価格Evidence中心の暫定判断を見直す",
                "related_hypothesis": "価格反応の背景要因",
                "related_evidence_ids": [],
            },
        ],
        "missing_information": [
            {
                "item": "直近ニュースとIR",
                "importance": "high",
                "reason": "価格変動の背景に材料があるかを確認するため",
            },
            {
                "item": "EDINET開示と決算指標",
                "importance": "medium",
                "reason": "短期価格反応と中期ファンダメンタルズを分けるため",
            },
            {
                "item": "同業比較と指数比較",
                "importance": "medium",
                "reason": "個別要因か市場全体の動きかを切り分けるため",
            },
        ],
        "used_evidence": used_evidence,
        "warnings": ["deterministic_baseline", "not_investment_advice"],
    }


def build_outputs(
    evidence: list[dict[str, Any]],
    *,
    target_id: str,
    stock_code: str,
    company_name: str,
    market: str,
    themes: list[str],
    report_date: str,
    run_id: str,
    run_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        build_agent_outputs(evidence, target_id=target_id, report_date=report_date, run_id=run_id),
        build_report_judge(
            evidence,
            target_id=target_id,
            stock_code=stock_code,
            company_name=company_name,
            market=market,
            themes=themes,
            run_id=run_id,
            run_at=run_at,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentTeam readout artifacts from Evidence JSON.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--theme", action="append", default=[], help="Theme label. Can be passed multiple times.")
    parser.add_argument("--report-date", help="YYYY-MM-DD. Defaults to the first evidence published date.")
    parser.add_argument("--run-id", help="Defaults to ATR-<report_date>-<stock_code>.")
    args = parser.parse_args()

    evidence = load_json(args.evidence)
    if not isinstance(evidence, list):
        raise ValueError("--evidence must contain an Evidence JSON array")
    if not evidence:
        raise ValueError("Evidence list is empty")

    first_identity = evidence[0].get("identity", {})
    report_date = args.report_date or str(first_identity.get("published_at", ""))[:10]
    if not report_date:
        raise ValueError("--report-date is required when evidence has no published_at")
    run_id = args.run_id or f"ATR-{report_date.replace('-', '')}-{args.stock_code}"
    run_at = now_jst()

    agent_outputs, report_judge = build_outputs(
        evidence,
        target_id=args.target_id,
        stock_code=args.stock_code,
        company_name=args.company_name,
        market=args.market,
        themes=args.theme,
        report_date=report_date,
        run_id=run_id,
        run_at=run_at,
    )

    agents_path = args.out_dir / "agent_outputs.json"
    judge_path = args.out_dir / "report_judge.json"
    write_json(agents_path, agent_outputs)
    write_json(judge_path, report_judge)
    print(f"agent_outputs_path={agents_path}")
    print(f"report_judge_path={judge_path}")
    print(f"evidence_count={len(evidence)}")
    print(f"market_readout={report_judge['market_readout']['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
