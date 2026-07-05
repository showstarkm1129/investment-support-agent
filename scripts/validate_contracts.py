#!/usr/bin/env python3
"""Validate JSON contracts and known project JSON artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator as JsonSchemaValidator
except ImportError:  # jsonschema<4 compatibility for system Python environments.
    from jsonschema import Draft7Validator as JsonSchemaValidator
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_FILES = [
    "system/contracts/evidence.schema.json",
    "system/contracts/agent_output.schema.json",
    "system/contracts/report_judge.schema.json",
    "system/contracts/chat_judge.schema.json",
    "system/contracts/health.schema.json",
    "system/contracts/flow_script.schema.json",
]

SAMPLE_PAIRS = [
    ("system/contracts/evidence.schema.json", "data/sample/evidence.json"),
    ("system/contracts/agent_output.schema.json", "data/sample/agent_outputs.json"),
    ("system/contracts/report_judge.schema.json", "data/sample/report_judge.json"),
    ("system/contracts/chat_judge.schema.json", "tests/fixtures/chat_judge.sample.json"),
    ("system/contracts/health.schema.json", "data/sample/health.json"),
]

FLOW_SCRIPT_SCHEMA = "system/contracts/flow_script.schema.json"
FLOW_SCRIPT_DIR = "system/config/flow_scripts"


@dataclass(frozen=True)
class JsonPair:
    schema: Path
    instance: Path


def rel(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def json_path(error: ValidationError) -> str:
    if not error.absolute_path:
        return "$"
    parts = []
    for part in error.absolute_path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        else:
            parts.append(f".{part}")
    return "$" + "".join(parts)


def validate_schema(path: Path) -> list[str]:
    try:
        schema = load_json(path)
        JsonSchemaValidator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        return [f"{rel(path)}: invalid schema: {exc}"]
    return []


def validate_pair(pair: JsonPair) -> list[str]:
    errors: list[str] = []
    try:
        schema = load_json(pair.schema)
        instance = load_json(pair.instance)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{rel(pair.instance)}: could not load JSON: {exc}"]

    try:
        validator = JsonSchemaValidator(schema)
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
            errors.append(f"{rel(pair.instance)} {json_path(error)}: {error.message}")
    except SchemaError as exc:
        errors.append(f"{rel(pair.schema)}: invalid schema: {exc}")
    return errors


def built_in_pairs(root: Path) -> list[JsonPair]:
    pairs = [JsonPair(root / schema, root / sample) for schema, sample in SAMPLE_PAIRS]
    flow_schema = root / FLOW_SCRIPT_SCHEMA
    flow_dir = root / FLOW_SCRIPT_DIR
    pairs.extend(JsonPair(flow_schema, path) for path in sorted(flow_dir.glob("*.json")))
    return pairs


def print_result(errors: list[str], checked_count: int) -> int:
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Contract validation failed: {len(errors)} error(s)")
        return 1
    print(f"OK: contract validation passed ({checked_count} check(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate JSON Schemas and JSON files.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--schemas-only", action="store_true", help="Only validate schema documents.")
    parser.add_argument("--samples-only", action="store_true", help="Only validate sample JSON pairs.")
    parser.add_argument("--flow-scripts-only", action="store_true", help="Only validate system/config/flow_scripts/*.json.")
    parser.add_argument("--schema", type=Path, help="Schema for an explicit validation pair.")
    parser.add_argument("--instance", type=Path, help="JSON instance for an explicit validation pair.")
    args = parser.parse_args()

    root = args.root.resolve()
    errors: list[str] = []
    checked_count = 0

    if bool(args.schema) != bool(args.instance):
        parser.error("--schema and --instance must be provided together")

    if args.schema and args.instance:
        schema_path = args.schema if args.schema.is_absolute() else root / args.schema
        instance_path = args.instance if args.instance.is_absolute() else root / args.instance
        pair = JsonPair(schema_path, instance_path)
        errors.extend(validate_schema(pair.schema))
        errors.extend(validate_pair(pair))
        return print_result(errors, 1)

    run_schemas = not args.samples_only and not args.flow_scripts_only
    run_samples = not args.schemas_only and not args.flow_scripts_only
    run_flow_scripts = not args.schemas_only and not args.samples_only

    if run_schemas:
        for rel_path in SCHEMA_FILES:
            checked_count += 1
            errors.extend(validate_schema(root / rel_path))

    if run_samples:
        for schema_rel, sample_rel in SAMPLE_PAIRS:
            checked_count += 1
            pair = JsonPair(root / schema_rel, root / sample_rel)
            errors.extend(validate_pair(pair))

    if run_flow_scripts:
        flow_paths = sorted((root / FLOW_SCRIPT_DIR).glob("*.json"))
        if not flow_paths:
            errors.append(f"{FLOW_SCRIPT_DIR}: no flow script JSON files found")
        for path in flow_paths:
            checked_count += 1
            errors.extend(validate_pair(JsonPair(root / FLOW_SCRIPT_SCHEMA, path)))

    return print_result(errors, checked_count)


if __name__ == "__main__":
    raise SystemExit(main())
