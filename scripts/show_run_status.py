#!/usr/bin/env python3
"""Print a concise status summary for a research pipeline run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_run_dir(*, run_dir: Path | None, manifest: Path | None) -> Path:
    if run_dir:
        return run_dir if run_dir.is_absolute() else ROOT / run_dir
    if manifest:
        manifest_path = manifest if manifest.is_absolute() else ROOT / manifest
        return manifest_path.parent
    raise ValueError("--run-dir or --manifest is required")


def read_optional_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def step_summary(status_payload: dict[str, Any] | None) -> tuple[str, str, str, list[str]]:
    if not isinstance(status_payload, dict):
        return "missing", "-", "-", []
    status = str(status_payload.get("status") or "unknown")
    current_step = str(status_payload.get("current_step") or "-")
    failed_step = str(status_payload.get("failed_step") or "-")
    steps = []
    for item in status_payload.get("steps", []):
        if isinstance(item, dict):
            steps.append(f"{item.get('agent_name', '?')}:{item.get('status', 'unknown')}")
    return status, current_step, failed_step, steps


def build_status_lines(run_dir: Path) -> list[str]:
    pipeline_manifest = read_optional_json(run_dir / "pipeline_manifest.json")
    pipeline_health = read_optional_json(run_dir / "health.json")
    sequence_status = read_optional_json(run_dir / "agent_sequence_status.json")
    sequence_manifest = read_optional_json(run_dir / "agent_sequence_manifest.json")

    lines = [f"run_dir: {run_dir}"]
    if isinstance(pipeline_manifest, dict):
        lines.append(f"pipeline_status: {pipeline_manifest.get('status', 'unknown')}")
        lines.append(f"run_id: {pipeline_manifest.get('run_id', '-')}")
        lines.append(f"provider: {pipeline_manifest.get('provider', '-')} model: {pipeline_manifest.get('model', '-')}")
    else:
        lines.append("pipeline_status: missing")

    if isinstance(pipeline_health, dict):
        stats = pipeline_health.get("stats", {})
        if isinstance(stats, dict):
            lines.append(
                "stats: "
                f"evidence={stats.get('evidence_total', '-')} "
                f"agent_success={stats.get('agent_success', '-')} "
                f"agent_failed={stats.get('agent_failed', '-')} "
                f"reports={stats.get('report_outputs', '-')}"
            )

    seq_status, current_step, failed_step, steps = step_summary(sequence_status)
    lines.append(f"agent_sequence_status: {seq_status}")
    lines.append(f"current_step: {current_step}")
    lines.append(f"failed_step: {failed_step}")
    if isinstance(sequence_manifest, dict):
        resumed_steps = sequence_manifest.get("resumed_steps", [])
        if isinstance(resumed_steps, list):
            lines.append(f"resumed_steps: {len(resumed_steps)}")
    if steps:
        lines.append("steps:")
        lines.extend(f"  - {item}" for item in steps)
    else:
        lines.append("steps: missing")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Show pipeline and sequential Agent progress for a run directory.")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    run_dir = resolve_run_dir(run_dir=args.run_dir, manifest=args.manifest)
    for line in build_status_lines(run_dir):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
