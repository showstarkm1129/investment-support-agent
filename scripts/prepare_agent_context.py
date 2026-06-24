#!/usr/bin/env python3
"""Prepare deterministic context files for Agent Team flow runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))

FLOW_CHOICES = (
    "morning_report",
    "close_report",
    "chat_quick",
    "chat_context",
    "chat_agent",
    "chat_research",
)

FLOW_TO_BUCKET = {
    "morning_report": "morning",
    "close_report": "close",
    "chat_quick": "chat",
    "chat_context": "chat",
    "chat_agent": "chat",
    "chat_research": "research",
}

FLOW_TO_DOC = {
    "morning_report": "flows/morning_report.md",
    "close_report": "flows/close_report.md",
    "chat_quick": "flows/chat_quick.md",
    "chat_context": "flows/chat_context.md",
    "chat_agent": "flows/chat_agent.md",
    "chat_research": "flows/chat_research.md",
}

FLOW_AGENT_ORDER = {
    "morning_report": [
        ["search_design"],
        ["connector:jquants", "connector:edinet", "connector:ir", "connector:news", "connector:macro_policy"],
        ["evidence_builder"],
        ["bull", "bear", "contradiction", "pricing"],
        ["report_judge"],
        ["health"],
    ],
    "close_report": [
        ["search_design"],
        ["connector:jquants", "connector:edinet", "connector:ir", "connector:news", "connector:macro_policy"],
        ["evidence_builder"],
        ["bull", "bear", "contradiction", "pricing"],
        ["report_judge"],
        ["health"],
        ["generate_reports", "generate_app_pages"],
    ],
    "chat_quick": [
        ["chat_judge"],
    ],
    "chat_context": [
        ["chat_judge"],
    ],
    "chat_agent": [
        ["chat_judge"],
        ["bull", "bear", "contradiction", "pricing"],
        ["chat_judge"],
    ],
    "chat_research": [
        ["chat_judge"],
        ["search_design"],
        ["connector:jquants", "connector:edinet", "connector:ir", "connector:news", "connector:macro_policy"],
        ["evidence_builder"],
        ["bull", "bear", "contradiction", "pricing"],
        ["chat_judge"],
        ["health"],
    ],
}

CONTRACTS = {
    "evidence": "contracts/evidence.schema.json",
    "agent_output": "contracts/agent_output.schema.json",
    "report_judge": "contracts/report_judge.schema.json",
    "chat_judge": "contracts/chat_judge.schema.json",
    "health": "contracts/health.schema.json",
    "artifact": "contracts/artifact_contract.md",
}


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def project_path(path: Path, root: Path = ROOT) -> Path:
    if path.is_absolute():
        return path
    return root / path


def rel(path: Path, root: Path = ROOT) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        value = resolved_path.relative_to(resolved_root)
    except ValueError:
        value = resolved_path
    return str(value).replace("\\", "/")


def find_target(config: dict[str, Any], target_id: str | None) -> dict[str, Any]:
    targets = config.get("targets", [])
    if not isinstance(targets, list) or not targets:
        raise ValueError("config must contain at least one target")
    if target_id is None:
        first = targets[0]
        if not isinstance(first, dict):
            raise ValueError("first target must be an object")
        return first
    for target in targets:
        if isinstance(target, dict) and target.get("target_id") == target_id:
            return target
    raise ValueError(f"target_id not found in config: {target_id}")


def expected_outputs(flow: str, run_dir: Path, root: Path = ROOT) -> dict[str, str]:
    outputs = {
        "manifest": rel(run_dir / "manifest.json", root),
        "context": rel(run_dir / "context.json", root),
    }
    if flow in {"morning_report", "close_report", "chat_research"}:
        outputs["evidence"] = rel(run_dir / "evidence.json", root)
        outputs["health"] = rel(run_dir / "health.json", root)
    if flow in {"morning_report", "close_report", "chat_agent", "chat_research"}:
        outputs["agent_outputs"] = rel(run_dir / "agent_outputs.json", root)
    if flow in {"morning_report", "close_report"}:
        outputs["report_judge"] = rel(run_dir / "report_judge.json", root)
    if flow.startswith("chat_"):
        outputs["chat_judge"] = rel(run_dir / "chat_judge.json", root)
    return outputs


def build_context(
    flow: str,
    target_id: str | None,
    run_id: str,
    run_dir: Path,
    config_path: Path = ROOT / "config/app.example.json",
    root: Path = ROOT,
) -> dict[str, Any]:
    if flow not in FLOW_CHOICES:
        raise ValueError(f"unknown flow: {flow}")

    config_path = project_path(config_path, root)
    run_dir = project_path(run_dir, root)
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    target = find_target(config, target_id)

    return {
        "schema_version": "agent_context_v1",
        "created_at": now_jst(),
        "run_id": run_id,
        "flow": flow,
        "bucket": FLOW_TO_BUCKET[flow],
        "target_id": target["target_id"],
        "target": target,
        "timezone": config.get("timezone", "Asia/Tokyo"),
        "flow_doc": FLOW_TO_DOC[flow],
        "error_policy": "flows/error_policy.md",
        "agent_order": FLOW_AGENT_ORDER[flow],
        "contracts": CONTRACTS,
        "inputs": {
            "app_config": rel(config_path, root),
            "targets_config": "config/targets.example.json",
            "sources_config": "config/sources.example.json",
            "runtime_config": "config/runtime.example.json",
            "sample_evidence": "data/sample/evidence.json",
            "sample_agent_outputs": "data/sample/agent_outputs.json",
            "sample_report_judge": "data/sample/report_judge.json",
            "sample_health": "data/sample/health.json",
        },
        "outputs": expected_outputs(flow, run_dir, root),
        "guardrails": [
            "Use evidence IDs for factual claims.",
            "Keep facts, interpretation, and uncertainty separate.",
            "Do not produce trade instructions.",
            "Validate artifacts against contracts before downstream use.",
        ],
    }


def write_context(context: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an Agent Team context JSON file.")
    parser.add_argument("--flow", choices=FLOW_CHOICES, required=True)
    parser.add_argument("--target-id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/app.example.json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    context = build_context(
        flow=args.flow,
        target_id=args.target_id,
        run_id=args.run_id,
        run_dir=args.run_dir,
        config_path=args.config,
    )
    if args.out:
        write_context(context, args.out)
        print(args.out)
    else:
        print(json.dumps(context, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
