#!/usr/bin/env python3
"""Check generated run, data, and report artifacts for basic contract health."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from validate_contracts import JsonPair, rel, validate_pair


ROOT = Path(__file__).resolve().parents[1]
RUN_BUCKETS = {"morning", "close", "chat", "research"}
STRICT_STATUSES = {"completed", "published"}

REQUIRED_DIRS = [
    "runs",
    "reports/daily",
    "reports/morning",
    "reports/weekly",
    "reports/notebooklm",
    "data/evidence",
    "data/agent_outputs",
    "data/judge_outputs",
    "data/health",
]

SCHEMA_BY_OUTPUT = {
    "evidence": "contracts/evidence.schema.json",
    "agent_outputs": "contracts/agent_output.schema.json",
    "report_judge": "contracts/report_judge.schema.json",
    "chat_judge": "contracts/chat_judge.schema.json",
    "health": "contracts/health.schema.json",
}


@dataclass
class ArtifactReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.error(message)

    def print_summary(self) -> int:
        for warning in self.warnings:
            print(f"WARN: {warning}")
        for error in self.errors:
            print(f"ERROR: {error}")
        if self.errors:
            print(f"Artifact check failed: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
            return 1
        print(f"OK: artifact check passed ({self.checked} item(s), {len(self.warnings)} warning(s))")
        return 0


def load_json(path: Path, report: ArtifactReport) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        report.error(f"{rel(path)}: could not load JSON: {exc}")
        return None


def project_path(path_text: str, root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def is_template_run_dir(path: Path) -> bool:
    return "YYYY-MM-DD" in path.parts or "target_id" in path.parts


def find_run_dirs(root: Path) -> list[Path]:
    run_root = root / "runs"
    if not run_root.exists():
        return []
    candidates = [
        path
        for path in run_root.glob("*/*/*")
        if path.is_dir() and path.name in RUN_BUCKETS and not is_template_run_dir(path)
    ]
    return sorted(candidates)


def validate_artifact_json(report: ArtifactReport, output_name: str, path: Path, root: Path) -> None:
    schema_rel = SCHEMA_BY_OUTPUT.get(output_name)
    if not schema_rel or not path.exists():
        return
    report.checked += 1
    for error in validate_pair(JsonPair(root / schema_rel, path)):
        report.error(error)


def check_required_dirs(report: ArtifactReport, root: Path) -> None:
    for rel_dir in REQUIRED_DIRS:
        report.checked += 1
        report.check((root / rel_dir).is_dir(), f"required artifact directory missing: {rel_dir}")


def check_report_files(report: ArtifactReport, root: Path) -> None:
    for path in sorted((root / "reports").glob("**/*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if path.suffix not in {".html", ".md", ".json"}:
            continue
        report.checked += 1
        if path.stat().st_size == 0:
            report.error(f"{rel(path)}: report artifact is empty")


def check_data_artifacts(report: ArtifactReport, root: Path) -> None:
    data_schema_dirs = {
        "evidence": root / "data/evidence",
        "agent_outputs": root / "data/agent_outputs",
        "health": root / "data/health",
    }
    for output_name, directory in data_schema_dirs.items():
        for path in sorted(directory.glob("*.json")):
            validate_artifact_json(report, output_name, path, root)

    for path in sorted((root / "data/judge_outputs").glob("*.json")):
        payload = load_json(path, report)
        if not isinstance(payload, dict):
            continue
        agent_name = payload.get("agent_name")
        output_name = "chat_judge" if agent_name == "chat_judge" else "report_judge"
        validate_artifact_json(report, output_name, path, root)


def check_run_dir(report: ArtifactReport, run_dir: Path, root: Path, strict: bool) -> None:
    report.checked += 1
    manifest_path = run_dir / "manifest.json"
    context_path = run_dir / "context.json"
    report.check(manifest_path.is_file(), f"{rel(run_dir)}: manifest.json is missing")
    report.check(context_path.is_file(), f"{rel(run_dir)}: context.json is missing")
    if not manifest_path.exists() or not context_path.exists():
        return

    manifest = load_json(manifest_path, report)
    context = load_json(context_path, report)
    if not isinstance(manifest, dict) or not isinstance(context, dict):
        return

    for key in ["schema_version", "run_id", "date", "target_id", "flow", "bucket", "status", "paths"]:
        if key not in manifest:
            report.error(f"{rel(manifest_path)}: missing key {key}")
    for key in ["schema_version", "run_id", "flow", "bucket", "target_id", "outputs"]:
        if key not in context:
            report.error(f"{rel(context_path)}: missing key {key}")

    if manifest.get("run_id") != context.get("run_id"):
        report.error(f"{rel(run_dir)}: manifest/context run_id mismatch")
    if manifest.get("flow") != context.get("flow"):
        report.error(f"{rel(run_dir)}: manifest/context flow mismatch")
    if manifest.get("bucket") != run_dir.name:
        report.error(f"{rel(run_dir)}: bucket does not match directory name")

    paths = manifest.get("paths", {})
    if isinstance(paths, dict):
        for name, path_text in paths.items():
            if not isinstance(path_text, str):
                report.error(f"{rel(manifest_path)} paths.{name}: must be a string")
                continue
            artifact_path = project_path(path_text, root)
            if not artifact_path.exists():
                report.error(f"{rel(manifest_path)} paths.{name}: missing {path_text}")

    outputs = context.get("outputs", {})
    status = manifest.get("status")
    require_outputs = strict or status in STRICT_STATUSES
    if isinstance(outputs, dict):
        for output_name, path_text in outputs.items():
            if not isinstance(path_text, str):
                report.error(f"{rel(context_path)} outputs.{output_name}: must be a string")
                continue
            output_path = project_path(path_text, root)
            if output_path.exists():
                validate_artifact_json(report, output_name, output_path, root)
            elif output_name in {"manifest", "context"} or require_outputs:
                report.error(f"{rel(context_path)} outputs.{output_name}: missing {path_text}")
            else:
                report.warn(f"{rel(context_path)} outputs.{output_name}: not created yet ({status})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check expected project artifacts.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run-dir", type=Path, help="Check a specific run directory.")
    parser.add_argument("--strict", action="store_true", help="Treat missing expected run outputs as errors.")
    args = parser.parse_args()

    root = args.root.resolve()
    report = ArtifactReport()
    check_required_dirs(report, root)
    check_report_files(report, root)
    check_data_artifacts(report, root)

    if args.run_dir:
        run_dir = args.run_dir if args.run_dir.is_absolute() else root / args.run_dir
        check_run_dir(report, run_dir, root, args.strict)
    else:
        run_dirs = find_run_dirs(root)
        if not run_dirs:
            report.warn("runs/: no concrete run directories found")
        for run_dir in run_dirs:
            check_run_dir(report, run_dir, root, args.strict)

    return report.print_summary()


if __name__ == "__main__":
    raise SystemExit(main())
