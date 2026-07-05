from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(rel: str) -> Any:
    with (ROOT / rel).open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise AssertionError(f"external refs are not supported in tests: {ref}")
    node: Any = schema
    for part in ref[2:].split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise AssertionError(f"ref did not resolve to object: {ref}")
    return node


def type_matches(expected: str, instance: Any) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    return True


def validate(schema_node: dict[str, Any], instance: Any, root_schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []

    if "$ref" in schema_node:
        return validate(resolve_ref(root_schema, schema_node["$ref"]), instance, root_schema, path)

    if "anyOf" in schema_node:
        branch_errors = [
            validate(branch, instance, root_schema, path)
            for branch in schema_node["anyOf"]
        ]
        if any(not item for item in branch_errors):
            return []
        return [f"{path}: did not match any allowed schema"]

    if "const" in schema_node and instance != schema_node["const"]:
        errors.append(f"{path}: expected const {schema_node['const']!r}, got {instance!r}")

    if "enum" in schema_node and instance not in schema_node["enum"]:
        errors.append(f"{path}: {instance!r} not in enum")

    expected_type = schema_node.get("type")
    if isinstance(expected_type, str) and not type_matches(expected_type, instance):
        errors.append(f"{path}: expected {expected_type}, got {type(instance).__name__}")
        return errors

    if isinstance(instance, str):
        pattern = schema_node.get("pattern")
        if isinstance(pattern, str) and not re.match(pattern, instance):
            errors.append(f"{path}: string does not match pattern {pattern}")
        min_length = schema_node.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(f"{path}: string shorter than {min_length}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema_node.get("minimum")
        maximum = schema_node.get("maximum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            errors.append(f"{path}: number lower than {minimum}")
        if isinstance(maximum, (int, float)) and instance > maximum:
            errors.append(f"{path}: number higher than {maximum}")

    if isinstance(instance, dict):
        required = schema_node.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required key {key}")

        properties = schema_node.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in instance and isinstance(child_schema, dict):
                    errors.extend(validate(child_schema, instance[key], root_schema, f"{path}.{key}"))

        additional = schema_node.get("additionalProperties", True)
        known_keys = set(properties) if isinstance(properties, dict) else set()
        extra_keys = set(instance) - known_keys
        if additional is False and extra_keys:
            errors.append(f"{path}: unexpected keys {sorted(extra_keys)}")
        elif isinstance(additional, dict):
            for key in extra_keys:
                errors.extend(validate(additional, instance[key], root_schema, f"{path}.{key}"))

    if isinstance(instance, list):
        min_items = schema_node.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append(f"{path}: fewer than {min_items} items")
        if schema_node.get("uniqueItems"):
            seen = {json.dumps(item, sort_keys=True) for item in instance}
            if len(seen) != len(instance):
                errors.append(f"{path}: items are not unique")
        item_schema = schema_node.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors.extend(validate(item_schema, item, root_schema, f"{path}[{index}]"))

    return errors


class ContractTests(unittest.TestCase):
    def test_schema_files_have_identity(self) -> None:
        for rel in [
            "system/contracts/evidence.schema.json",
            "system/contracts/agent_output.schema.json",
            "system/contracts/report_judge.schema.json",
            "system/contracts/chat_judge.schema.json",
            "system/contracts/health.schema.json",
            "system/contracts/flow_script.schema.json",
        ]:
            schema = load_json(rel)
            self.assertIn("$schema", schema)
            self.assertIn("$id", schema)
            self.assertIn("title", schema)

    def test_samples_match_contracts(self) -> None:
        pairs = [
            ("system/contracts/evidence.schema.json", "data/sample/evidence.json"),
            ("system/contracts/agent_output.schema.json", "data/sample/agent_outputs.json"),
            ("system/contracts/report_judge.schema.json", "data/sample/report_judge.json"),
            ("system/contracts/health.schema.json", "data/sample/health.json"),
            ("system/contracts/chat_judge.schema.json", "tests/fixtures/chat_judge.sample.json"),
            ("system/contracts/flow_script.schema.json", "system/config/flow_scripts/semiconductor_sector_morning.json"),
        ]
        for schema_rel, sample_rel in pairs:
            with self.subTest(schema=schema_rel, sample=sample_rel):
                schema = load_json(schema_rel)
                sample = load_json(sample_rel)
                errors = validate(schema, sample, schema)
                self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
