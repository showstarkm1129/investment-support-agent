#!/usr/bin/env python3
"""Create run folders and optional Agent Team command execution metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from prepare_agent_context import (
    FLOW_CHOICES,
    FLOW_TO_BUCKET,
    ROOT,
    build_context,
    load_json,
    project_path,
    rel,
    write_context,
)


JST = timezone(timedelta(hours=9))


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def default_run_id(flow: str, date: str, target_id: str) -> str:
    compact_date = date.replace("-", "")
    compact_flow = flow.replace("_", "-").upper()
    safe_target = target_id.replace("/", "-")
    return f"RUN{compact_date}-{safe_target}-{compact_flow}"


def select_target_id(config_path: Path, explicit_target_id: str | None) -> str:
    if explicit_target_id:
        return explicit_target_id
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    targets = config.get("targets", [])
    if not isinstance(targets, list) or not targets or not isinstance(targets[0], dict):
        raise ValueError("config must contain at least one target")
    target_id = targets[0].get("target_id")
    if not isinstance(target_id, str) or not target_id:
        raise ValueError("first target must have target_id")
    return target_id


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_manifest(
    *,
    run_id: str,
    flow: str,
    date: str,
    target_id: str,
    run_dir: Path,
    context_path: Path,
    root: Path,
    status: str,
    agent_command: list[str] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "run_manifest_v1",
        "created_at": now_jst(),
        "updated_at": now_jst(),
        "run_id": run_id,
        "date": date,
        "target_id": target_id,
        "flow": flow,
        "bucket": FLOW_TO_BUCKET[flow],
        "status": status,
        "paths": {
            "run_dir": rel(run_dir, root),
            "manifest": rel(run_dir / "manifest.json", root),
            "context": rel(context_path, root),
        },
        "agent_command": agent_command,
        "returncode": None,
    }


def run_agent_command(command: list[str], context_path: Path, run_dir: Path) -> int:
    env = os.environ.copy()
    env["AGENT_CONTEXT_JSON"] = str(context_path)
    env["AGENT_RUN_DIR"] = str(run_dir)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, check=False)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and optionally run an Agent Team flow.")
    parser.add_argument("--flow", choices=FLOW_CHOICES, required=True)
    parser.add_argument("--target-id")
    parser.add_argument("--date", default=today_jst())
    parser.add_argument("--run-id")
    parser.add_argument("--config", type=Path, default=ROOT / "config/app.example.json")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    parser.add_argument(
        "--agent-command",
        nargs=argparse.REMAINDER,
        help="Optional command to run after context creation. Everything after this flag is executed.",
    )
    args = parser.parse_args()

    config_path = project_path(args.config)
    runs_dir = project_path(args.runs_dir)
    target_id = select_target_id(config_path, args.target_id)
    run_id = args.run_id or default_run_id(args.flow, args.date, target_id)
    bucket = FLOW_TO_BUCKET[args.flow]
    run_dir = runs_dir / args.date / target_id / bucket
    context_path = run_dir / "context.json"
    manifest_path = run_dir / "manifest.json"

    run_dir.mkdir(parents=True, exist_ok=True)
    context = build_context(
        flow=args.flow,
        target_id=target_id,
        run_id=run_id,
        run_dir=run_dir,
        config_path=config_path,
    )
    write_context(context, context_path)

    agent_command = args.agent_command or None
    manifest = build_manifest(
        run_id=run_id,
        flow=args.flow,
        date=args.date,
        target_id=target_id,
        run_dir=run_dir,
        context_path=context_path,
        root=ROOT,
        status="prepared",
        agent_command=agent_command,
    )
    write_manifest(manifest_path, manifest)

    returncode = 0
    if agent_command:
        manifest["status"] = "running"
        manifest["updated_at"] = now_jst()
        write_manifest(manifest_path, manifest)
        returncode = run_agent_command(agent_command, context_path, run_dir)
        manifest["status"] = "completed" if returncode == 0 else "failed"
        manifest["returncode"] = returncode
        manifest["updated_at"] = now_jst()
        write_manifest(manifest_path, manifest)

    print(f"manifest: {manifest_path}")
    print(f"context: {context_path}")
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
