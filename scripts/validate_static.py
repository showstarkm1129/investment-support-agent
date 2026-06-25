#!/usr/bin/env python3
"""Static maintenance checks for the MVP investment support agent project.

The validator intentionally avoids network calls. It checks the files that are
easy to break during maintenance: JSON structure, cross references, generated
artifacts, local HTML links, and core project conventions.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "agents/AGENTS.md",
    "agents/search_design/AGENTS.md",
    "agents/evidence_builder/AGENTS.md",
    "agents/bull/AGENTS.md",
    "agents/bear/AGENTS.md",
    "agents/contradiction/AGENTS.md",
    "agents/pricing/AGENTS.md",
    "agents/report_judge/AGENTS.md",
    "agents/chat_judge/AGENTS.md",
    "app/assets/app.css",
    "app/dashboard.html",
    "app/evidence.html",
    "app/health.html",
    "app/agents.html",
    "app/flow_builder.html",
    "config/app.example.json",
    "config/targets.example.json",
    "config/sources.example.json",
    "config/runtime.example.json",
    "config/auto_search.example.json",
    "config/flow_scripts/README.md",
    "config/flow_scripts/semiconductor_sector_morning.json",
    "flows/README.md",
    "flows/morning_report.md",
    "flows/close_report.md",
    "flows/chat_quick.md",
    "flows/chat_context.md",
    "flows/chat_agent.md",
    "flows/chat_research.md",
    "flows/error_policy.md",
    "contracts/README.md",
    "contracts/evidence.schema.json",
    "contracts/agent_output.schema.json",
    "contracts/report_judge.schema.json",
    "contracts/chat_judge.schema.json",
    "contracts/health.schema.json",
    "contracts/flow_script.schema.json",
    "contracts/artifact_contract.md",
    "connectors/README.md",
    "connectors/jquants/README.md",
    "connectors/edinet/README.md",
    "connectors/ir/README.md",
    "connectors/news/README.md",
    "connectors/macro_policy/README.md",
    "data/sample/evidence.json",
    "data/sample/agent_outputs.json",
    "data/sample/report_judge.json",
    "data/sample/health.json",
    "data/raw/.gitkeep",
    "data/normalized/.gitkeep",
    "data/evidence/.gitkeep",
    "data/agent_outputs/.gitkeep",
    "data/judge_outputs/.gitkeep",
    "data/health/.gitkeep",
    "data/chat_logs/.gitkeep",
    "runs/README.md",
    "runs/YYYY-MM-DD/target_id/morning/.gitkeep",
    "runs/YYYY-MM-DD/target_id/close/.gitkeep",
    "runs/YYYY-MM-DD/target_id/chat/.gitkeep",
    "runs/YYYY-MM-DD/target_id/research/.gitkeep",
    "reports/daily/2026-06-22_6501_close.html",
    "reports/daily/2026-06-22_6501_close_analysis.md",
    "reports/daily/2026-06-22_6501_close_audio.md",
    "reports/morning/.gitkeep",
    "reports/weekly/.gitkeep",
    "reports/notebooklm/.gitkeep",
    "scripts/generate_reports.py",
    "scripts/generate_app_pages.py",
    "scripts/run_flow.py",
    "scripts/flow_server.py",
    "scripts/prepare_agent_context.py",
    "tests/test_contracts.py",
    "tests/test_flow_integrity.py",
    "tests/test_static_validation.py",
    "tests/fixtures/chat_judge.sample.json",
    "docs/architecture.md",
    "docs/flow_builder.md",
    "docs/operations.md",
    "docs/onboarding_agent_teams.md",
    "docs/project_structure.md",
]

HTML_FILES = [
    "app/dashboard.html",
    "app/evidence.html",
    "app/health.html",
    "app/agents.html",
    "app/flow_builder.html",
    "Evidence画面プロトタイプ.html",
]

EXPECTED_NAV_LABELS = ["Dashboard", "Evidence", "Report", "Health", "Flow", "Agent指示書"]

SCRIPT_FILES = [
    "scripts/generate_reports.py",
    "scripts/generate_app_pages.py",
    "scripts/validate_static.py",
    "scripts/run_flow.py",
    "scripts/flow_server.py",
    "scripts/prepare_agent_context.py",
]

FLOW_FILES = [
    "flows/morning_report.md",
    "flows/close_report.md",
    "flows/chat_quick.md",
    "flows/chat_context.md",
    "flows/chat_agent.md",
    "flows/chat_research.md",
]

CONTRACT_SCHEMA_FILES = [
    "contracts/evidence.schema.json",
    "contracts/agent_output.schema.json",
    "contracts/report_judge.schema.json",
    "contracts/chat_judge.schema.json",
    "contracts/health.schema.json",
    "contracts/flow_script.schema.json",
]

CONFIG_EXAMPLE_FILES = [
    "config/app.example.json",
    "config/targets.example.json",
    "config/sources.example.json",
    "config/runtime.example.json",
    "config/auto_search.example.json",
]

ALLOWED_SOURCE_TYPES = {
    "price_volume",
    "financial",
    "market_supply",
    "disclosure_edinet",
    "ir",
    "news",
    "macro_policy",
    "event",
}
ALLOWED_RELIABILITY = {"A", "B", "C", "D", "E"}
ALLOWED_LEVELS = {"high", "medium", "low"}
ALLOWED_DIRECTION_HINTS = {
    "bullish",
    "bearish",
    "contradiction",
    "priced_in",
    "neutral",
    "unknown",
}
ALLOWED_REVIEW_STATUS = {"unread", "reviewed", "ignored"}
ALLOWED_AGENTS = {"bull", "bear", "contradiction", "pricing"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_JUDGE_LABELS = {
    "bullish",
    "slightly_bullish",
    "neutral",
    "pending",
    "slightly_bearish",
    "bearish",
}
ALLOWED_INFORMATION_STATUS = {
    "bullish_evidence_leading",
    "bearish_evidence_leading",
    "mixed",
    "insufficient_information",
    "no_material_change",
}
ALLOWED_HYPOTHESIS_IMPACT = {
    "supportive",
    "slightly_supportive",
    "neutral",
    "slightly_negative",
    "negative",
    "undetermined",
}
ALLOWED_HEALTH_STATUS = {"ok", "warn", "error", "info", "skipped"}
ALLOWED_FLOWS = {
    "morning_report",
    "close_report",
    "chat_quick",
    "chat_context",
    "chat_agent",
    "chat_research",
}
ALLOWED_PROVIDERS = {"manual", "codex", "claude", "openai_api", "anthropic_api", "gemini_api"}
ALLOWED_RUN_MODES = {"prepare", "dry-run", "simulate", "live"}

FORBIDDEN_ADVICE_PATTERNS = [
    r"買うべき",
    r"売るべき",
    r"保有継続",
    r"撤退検討",
    r"追加買い",
    r"損切りすべき",
    r"利確すべき",
    r"recommended_actions",
]


@dataclass
class Finding:
    level: str
    message: str


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def error(self, message: str) -> None:
        self.findings.append(Finding("ERROR", message))

    def warn(self, message: str) -> None:
        self.findings.append(Finding("WARN", message))

    def pass_count(self) -> int:
        return sum(1 for finding in self.findings if finding.level == "PASS")

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.error(message)

    def print_summary(self) -> int:
        errors = [item for item in self.findings if item.level == "ERROR"]
        warnings = [item for item in self.findings if item.level == "WARN"]
        if not errors and not warnings:
            print("OK: static validation passed")
            return 0

        for item in self.findings:
            print(f"{item.level}: {item.message}")
        print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1 if errors else 0


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.nav_labels: list[str] = []
        self._in_nav_link = False
        self._current_nav_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {name: value for name, value in attrs}
        class_value = attr_dict.get("class") or ""
        if tag == "a" and "nav-link" in class_value.split():
            self._in_nav_link = True
            self._current_nav_text = []
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.links.append((name, value))

    def handle_data(self, data: str) -> None:
        if self._in_nav_link:
            self._current_nav_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_nav_link:
            label = "".join(self._current_nav_text).strip()
            if label:
                self.nav_labels.append(label)
            self._in_nav_link = False
            self._current_nav_text = []


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def require_keys(v: Validator, obj: dict[str, Any], keys: list[str], path: str) -> None:
    for key in keys:
        if key not in obj:
            v.error(f"{path}: missing key '{key}'")


def ensure_type(v: Validator, value: Any, expected: type, path: str) -> None:
    if not isinstance(value, expected):
        v.error(f"{path}: expected {expected.__name__}, got {type(value).__name__}")


def is_iso_datetime(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2}$", value))


def is_date(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))


def check_required_files(v: Validator) -> None:
    for rel in REQUIRED_FILES:
        v.check((v.root / rel).exists(), f"required file missing: {rel}")


def check_flow_docs(v: Validator) -> None:
    for rel in FLOW_FILES:
        path = v.root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for section in ["## Inputs", "## Order", "## Outputs"]:
            if section not in text:
                v.error(f"{rel}: missing flow section {section}")
        if "contracts/" not in text and "schema" not in text:
            v.warn(f"{rel}: no contract reference found")

    error_policy = v.root / "flows/error_policy.md"
    if error_policy.exists():
        text = error_policy.read_text(encoding="utf-8")
        for token in ["## Principles", "## Severity", "## Required Handling"]:
            if token not in text:
                v.error(f"flows/error_policy.md: missing section {token}")


def check_contract_schemas(v: Validator) -> None:
    for rel in CONTRACT_SCHEMA_FILES:
        path = v.root / rel
        if not path.exists():
            continue
        schema = load_json(path)
        ensure_type(v, schema, dict, rel)
        if not isinstance(schema, dict):
            continue
        for key in ["$schema", "$id", "title", "type"]:
            if key not in schema:
                v.error(f"{rel}: missing schema key {key}")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            v.error(f"{rel}: unexpected JSON Schema draft")

    artifact_contract = v.root / "contracts/artifact_contract.md"
    if artifact_contract.exists():
        text = artifact_contract.read_text(encoding="utf-8")
        for token in ["manifest.json", "context.json", "runs/{YYYY-MM-DD}/{target_id}/{bucket}/"]:
            if token not in text:
                v.error(f"contracts/artifact_contract.md: missing artifact rule {token}")


def check_config_examples(v: Validator) -> None:
    for rel in CONFIG_EXAMPLE_FILES:
        path = v.root / rel
        if not path.exists():
            continue
        config = load_json(path)
        ensure_type(v, config, dict, rel)
        if isinstance(config, dict) and "schema_version" not in config:
            v.error(f"{rel}: missing schema_version")


def check_python_syntax(v: Validator) -> None:
    for rel in SCRIPT_FILES:
        path = v.root / rel
        if not path.exists():
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            v.error(f"{rel}: Python syntax error at line {exc.lineno}: {exc.msg}")


def check_evidence(v: Validator, evidence: Any) -> set[str]:
    ensure_type(v, evidence, list, "data/sample/evidence.json")
    ids: set[str] = set()
    if not isinstance(evidence, list):
        return ids

    for index, item in enumerate(evidence):
        path = f"evidence[{index}]"
        ensure_type(v, item, dict, path)
        if not isinstance(item, dict):
            continue
        require_keys(v, item, ["schema_version", "evidence_id", "identity", "source", "content", "evaluation", "workflow"], path)
        evidence_id = item.get("evidence_id")
        if isinstance(evidence_id, str):
            if evidence_id in ids:
                v.error(f"{path}: duplicated evidence_id {evidence_id}")
            ids.add(evidence_id)
        else:
            v.error(f"{path}: evidence_id must be string")

        identity = item.get("identity", {})
        source = item.get("source", {})
        content = item.get("content", {})
        evaluation = item.get("evaluation", {})
        workflow = item.get("workflow", {})
        for obj, keys, obj_path in [
            (identity, ["target_id", "stock_code", "company_name", "collected_at", "published_at"], f"{path}.identity"),
            (source, ["source_type", "source_name", "source_reliability", "save_policy"], f"{path}.source"),
            (content, ["title", "summary", "metrics"], f"{path}.content"),
            (evaluation, ["directness", "freshness", "impact_level", "direction_hint", "hypothesis_impact", "usable_for_judgement"], f"{path}.evaluation"),
            (workflow, ["human_review_status", "used_in_decision", "review_due_date", "related_evidence_ids"], f"{path}.workflow"),
        ]:
            ensure_type(v, obj, dict, obj_path)
            if isinstance(obj, dict):
                require_keys(v, obj, keys, obj_path)

        if isinstance(identity, dict):
            for key in ["collected_at", "published_at"]:
                value = identity.get(key)
                if isinstance(value, str):
                    v.check(is_iso_datetime(value), f"{path}.identity.{key}: must be ISO datetime with timezone")

        if isinstance(source, dict):
            v.check(source.get("source_type") in ALLOWED_SOURCE_TYPES, f"{path}.source.source_type: unknown value {source.get('source_type')!r}")
            v.check(source.get("source_reliability") in ALLOWED_RELIABILITY, f"{path}.source.source_reliability: unknown value {source.get('source_reliability')!r}")

        if isinstance(evaluation, dict):
            for key in ["directness", "freshness", "impact_level"]:
                v.check(evaluation.get(key) in ALLOWED_LEVELS, f"{path}.evaluation.{key}: unknown value {evaluation.get(key)!r}")
            v.check(evaluation.get("direction_hint") in ALLOWED_DIRECTION_HINTS, f"{path}.evaluation.direction_hint: unknown value {evaluation.get('direction_hint')!r}")

        if isinstance(workflow, dict):
            v.check(workflow.get("human_review_status") in ALLOWED_REVIEW_STATUS, f"{path}.workflow.human_review_status: unknown value {workflow.get('human_review_status')!r}")
            review_due = workflow.get("review_due_date")
            if review_due is not None:
                v.check(isinstance(review_due, str) and is_date(review_due), f"{path}.workflow.review_due_date: must be YYYY-MM-DD or null")
            related = workflow.get("related_evidence_ids", [])
            ensure_type(v, related, list, f"{path}.workflow.related_evidence_ids")

    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        workflow = item.get("workflow", {})
        if not isinstance(workflow, dict):
            continue
        for related_id in workflow.get("related_evidence_ids", []):
            if related_id not in ids:
                v.error(f"evidence[{index}].workflow.related_evidence_ids: unknown evidence_id {related_id}")
    return ids


def check_agents(v: Validator, agent_bundle: Any, evidence_ids: set[str]) -> None:
    ensure_type(v, agent_bundle, dict, "data/sample/agent_outputs.json")
    if not isinstance(agent_bundle, dict):
        return
    require_keys(v, agent_bundle, ["schema_version", "target_id", "report_date", "agent_outputs"], "agent_outputs")
    if isinstance(agent_bundle.get("report_date"), str):
        v.check(is_date(agent_bundle["report_date"]), "agent_outputs.report_date: must be YYYY-MM-DD")

    outputs = agent_bundle.get("agent_outputs", [])
    ensure_type(v, outputs, list, "agent_outputs.agent_outputs")
    seen_agents: set[str] = set()
    if not isinstance(outputs, list):
        return

    for index, item in enumerate(outputs):
        path = f"agent_outputs[{index}]"
        ensure_type(v, item, dict, path)
        if not isinstance(item, dict):
            continue
        require_keys(v, item, ["agent_name", "run_id", "stance", "conclusion", "claim_strength", "confidence", "evidence_ids", "key_points", "limitations"], path)
        agent_name = item.get("agent_name")
        v.check(agent_name in ALLOWED_AGENTS, f"{path}.agent_name: unknown value {agent_name!r}")
        if isinstance(agent_name, str):
            if agent_name in seen_agents:
                v.error(f"{path}.agent_name: duplicated agent {agent_name}")
            seen_agents.add(agent_name)
        strength = item.get("claim_strength")
        v.check(isinstance(strength, int) and 0 <= strength <= 100, f"{path}.claim_strength: must be 0..100")
        v.check(item.get("confidence") in ALLOWED_CONFIDENCE, f"{path}.confidence: unknown value {item.get('confidence')!r}")
        evidence_refs = item.get("evidence_ids", [])
        ensure_type(v, evidence_refs, list, f"{path}.evidence_ids")
        if isinstance(evidence_refs, list):
            for evidence_id in evidence_refs:
                if evidence_id not in evidence_ids:
                    v.error(f"{path}.evidence_ids: unknown evidence_id {evidence_id}")
        for list_key in ["key_points", "limitations"]:
            ensure_type(v, item.get(list_key), list, f"{path}.{list_key}")

    missing_agents = ALLOWED_AGENTS - seen_agents
    for agent in sorted(missing_agents):
        v.error(f"agent_outputs: missing required agent '{agent}'")


def check_judge(v: Validator, judge: Any, evidence_ids: set[str]) -> None:
    ensure_type(v, judge, dict, "data/sample/report_judge.json")
    if not isinstance(judge, dict):
        return
    require_keys(
        v,
        judge,
        [
            "schema_version",
            "run_id",
            "agent_name",
            "run_at",
            "target",
            "judgement",
            "information_status",
            "hypothesis_impact",
            "uncertainty",
            "evidence_weight",
            "view_change_conditions",
            "missing_information",
            "used_evidence",
        ],
        "report_judge",
    )
    if isinstance(judge.get("run_at"), str):
        v.check(is_iso_datetime(judge["run_at"]), "report_judge.run_at: must be ISO datetime with timezone")

    judgement = judge.get("judgement", {})
    ensure_type(v, judgement, dict, "report_judge.judgement")
    if isinstance(judgement, dict):
        v.check(judgement.get("label") in ALLOWED_JUDGE_LABELS, f"report_judge.judgement.label: unknown value {judgement.get('label')!r}")
        score = judgement.get("direction_score")
        v.check(isinstance(score, int) and -100 <= score <= 100, "report_judge.judgement.direction_score: must be -100..100")
        v.check(judgement.get("confidence") in ALLOWED_CONFIDENCE, f"report_judge.judgement.confidence: unknown value {judgement.get('confidence')!r}")

    info = judge.get("information_status", {})
    hypo = judge.get("hypothesis_impact", {})
    uncertainty = judge.get("uncertainty", {})
    weights = judge.get("evidence_weight", {})
    if isinstance(info, dict):
        v.check(info.get("label") in ALLOWED_INFORMATION_STATUS, f"report_judge.information_status.label: unknown value {info.get('label')!r}")
    if isinstance(hypo, dict):
        v.check(hypo.get("label") in ALLOWED_HYPOTHESIS_IMPACT, f"report_judge.hypothesis_impact.label: unknown value {hypo.get('label')!r}")
    if isinstance(uncertainty, dict):
        v.check(uncertainty.get("level") in ALLOWED_CONFIDENCE, f"report_judge.uncertainty.level: unknown value {uncertainty.get('level')!r}")
        ensure_type(v, uncertainty.get("factors"), list, "report_judge.uncertainty.factors")
    if isinstance(weights, dict):
        for key in ["bullish", "bearish", "contradiction", "priced_in"]:
            v.check(isinstance(weights.get(key), int), f"report_judge.evidence_weight.{key}: must be integer")
        if all(isinstance(weights.get(key), int) for key in ["bullish", "bearish", "contradiction", "priced_in"]):
            total = sum(weights[key] for key in ["bullish", "bearish", "contradiction", "priced_in"])
            v.check(total == 100, f"report_judge.evidence_weight: must sum to 100, got {total}")

    for list_key in ["view_change_conditions", "missing_information", "used_evidence"]:
        ensure_type(v, judge.get(list_key), list, f"report_judge.{list_key}")

    for index, item in enumerate(judge.get("used_evidence", [])):
        if not isinstance(item, dict):
            v.error(f"report_judge.used_evidence[{index}]: must be object")
            continue
        evidence_id = item.get("evidence_id")
        if evidence_id not in evidence_ids:
            v.error(f"report_judge.used_evidence[{index}]: unknown evidence_id {evidence_id}")

    for index, item in enumerate(judge.get("view_change_conditions", [])):
        if not isinstance(item, dict):
            v.error(f"report_judge.view_change_conditions[{index}]: must be object")
            continue
        require_keys(v, item, ["condition", "effect", "related_hypothesis", "related_evidence_ids"], f"report_judge.view_change_conditions[{index}]")
        related = item.get("related_evidence_ids", [])
        ensure_type(v, related, list, f"report_judge.view_change_conditions[{index}].related_evidence_ids")
        if isinstance(related, list):
            for evidence_id in related:
                if evidence_id not in evidence_ids:
                    v.error(f"report_judge.view_change_conditions[{index}]: unknown evidence_id {evidence_id}")


def check_health(v: Validator, health: Any, evidence_count: int, agent_count: int) -> None:
    ensure_type(v, health, dict, "data/sample/health.json")
    if not isinstance(health, dict):
        return
    require_keys(v, health, ["schema_version", "run_id", "run_at", "overall_status", "summary", "stats", "sections"], "health")
    v.check(health.get("overall_status") in ALLOWED_HEALTH_STATUS, f"health.overall_status: unknown value {health.get('overall_status')!r}")
    stats = health.get("stats", {})
    ensure_type(v, stats, dict, "health.stats")
    if isinstance(stats, dict):
        if "evidence_total" in stats:
            v.check(stats["evidence_total"] == evidence_count, f"health.stats.evidence_total: expected {evidence_count}, got {stats['evidence_total']}")
        if "agent_success" in stats:
            v.check(stats["agent_success"] == agent_count, f"health.stats.agent_success: expected {agent_count}, got {stats['agent_success']}")
        if "ui_pages" in stats:
            app_pages = len(list((v.root / "app").glob("*.html")))
            v.check(stats["ui_pages"] == app_pages, f"health.stats.ui_pages: expected {app_pages}, got {stats['ui_pages']}")

    sections = health.get("sections", [])
    ensure_type(v, sections, list, "health.sections")
    if isinstance(sections, list):
        for section_index, section in enumerate(sections):
            if not isinstance(section, dict):
                v.error(f"health.sections[{section_index}]: must be object")
                continue
            checks = section.get("checks", [])
            ensure_type(v, checks, list, f"health.sections[{section_index}].checks")
            if not isinstance(checks, list):
                continue
            for check_index, check in enumerate(checks):
                path = f"health.sections[{section_index}].checks[{check_index}]"
                if not isinstance(check, dict):
                    v.error(f"{path}: must be object")
                    continue
                require_keys(v, check, ["check_id", "label", "status", "message", "detail"], path)
                v.check(check.get("status") in ALLOWED_HEALTH_STATUS, f"{path}.status: unknown value {check.get('status')!r}")


def check_config(v: Validator, config: Any) -> None:
    ensure_type(v, config, dict, "config/app.example.json")
    if not isinstance(config, dict):
        return
    require_keys(v, config, ["schema_version", "timezone", "targets", "report_schedule", "notebooklm"], "config")
    targets = config.get("targets", [])
    ensure_type(v, targets, list, "config.targets")
    if isinstance(targets, list):
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                v.error(f"config.targets[{index}]: must be object")
                continue
            require_keys(v, target, ["target_id", "target_type", "stock_code", "company_name", "themes", "auto_report_enabled"], f"config.targets[{index}]")


def check_flow_scripts(v: Validator) -> set[str]:
    script_ids: set[str] = set()
    script_dir = v.root / "config/flow_scripts"
    paths = sorted(script_dir.glob("*.json"))
    if not paths:
        v.error("config/flow_scripts: no flow scripts found")
        return script_ids

    for path in paths:
        rel_path = path.relative_to(v.root).as_posix()
        script = load_json(path)
        ensure_type(v, script, dict, rel_path)
        if not isinstance(script, dict):
            continue
        require_keys(v, script, ["schema_version", "script_id", "display_name", "flow", "target", "agent_groups", "agents"], rel_path)
        v.check(script.get("schema_version") == "flow_script_v1", f"{rel_path}: schema_version must be flow_script_v1")
        script_id = script.get("script_id")
        if isinstance(script_id, str):
            v.check(script_id == path.stem, f"{rel_path}: script_id must match filename")
            v.check(bool(re.match(r"^[a-z0-9][a-z0-9_-]*$", script_id)), f"{rel_path}: script_id has invalid characters")
            script_ids.add(script_id)
        else:
            v.error(f"{rel_path}: script_id must be string")

        v.check(script.get("flow") in ALLOWED_FLOWS, f"{rel_path}: unknown flow {script.get('flow')!r}")
        if "provider" in script:
            v.check(script.get("provider") in ALLOWED_PROVIDERS, f"{rel_path}: unknown provider {script.get('provider')!r}")
        if "model" in script:
            v.check(isinstance(script.get("model"), str) and bool(script.get("model")), f"{rel_path}: model must be non-empty string")
        if "mode" in script:
            v.check(script.get("mode") in ALLOWED_RUN_MODES, f"{rel_path}: unknown mode {script.get('mode')!r}")

        target = script.get("target", {})
        ensure_type(v, target, dict, f"{rel_path}.target")
        if isinstance(target, dict):
            require_keys(v, target, ["target_id", "target_type", "company_name", "themes"], f"{rel_path}.target")
            ensure_type(v, target.get("themes"), list, f"{rel_path}.target.themes")

        groups = script.get("agent_groups", [])
        agents = script.get("agents", [])
        ensure_type(v, groups, list, f"{rel_path}.agent_groups")
        ensure_type(v, agents, list, f"{rel_path}.agents")
        step_ids = {
            item.get("agent_id")
            for item in agents
            if isinstance(item, dict) and isinstance(item.get("agent_id"), str)
        }
        if isinstance(groups, list):
            for index, group in enumerate(groups):
                group_path = f"{rel_path}.agent_groups[{index}]"
                ensure_type(v, group, dict, group_path)
                if not isinstance(group, dict):
                    continue
                require_keys(v, group, ["group_id", "agents"], group_path)
                group_agents = group.get("agents", [])
                ensure_type(v, group_agents, list, f"{group_path}.agents")
                if isinstance(group_agents, list):
                    for agent_id in group_agents:
                        v.check(isinstance(agent_id, str) and bool(agent_id), f"{group_path}.agents: agent id must be non-empty string")
                        if isinstance(agent_id, str) and step_ids:
                            v.check(agent_id in step_ids, f"{group_path}.agents: missing step definition for {agent_id}")
    return script_ids


def check_auto_search(v: Validator, script_ids: set[str]) -> None:
    path = v.root / "config/auto_search.example.json"
    if not path.exists():
        return
    config = load_json(path)
    ensure_type(v, config, dict, "config/auto_search.example.json")
    if not isinstance(config, dict):
        return
    require_keys(v, config, ["schema_version", "timezone", "routes"], "config/auto_search.example.json")
    v.check(config.get("schema_version") == "auto_search_config_v1", "config/auto_search.example.json: unexpected schema_version")
    routes = config.get("routes", [])
    ensure_type(v, routes, list, "config/auto_search.example.json.routes")
    if not isinstance(routes, list):
        return
    for index, route in enumerate(routes):
        route_path = f"config/auto_search.example.json.routes[{index}]"
        ensure_type(v, route, dict, route_path)
        if not isinstance(route, dict):
            continue
        require_keys(v, route, ["route_id", "enabled", "time", "script_id", "provider", "mode"], route_path)
        script_id = route.get("script_id")
        v.check(script_id in script_ids, f"{route_path}.script_id: unknown script {script_id!r}")
        v.check(route.get("provider") in ALLOWED_PROVIDERS, f"{route_path}.provider: unknown value {route.get('provider')!r}")
        if "model" in route:
            v.check(isinstance(route.get("model"), str) and bool(route.get("model")), f"{route_path}.model: must be non-empty string")
        v.check(route.get("mode") in ALLOWED_RUN_MODES, f"{route_path}.mode: unknown value {route.get('mode')!r}")


def check_html_links(v: Validator) -> None:
    for rel in HTML_FILES:
        path = v.root / rel
        if not path.exists():
            continue
        parser = LinkParser()
        parser.feed(path.read_text(encoding="utf-8"))
        if rel.startswith("app/") or rel.startswith("reports/"):
            v.check(
                parser.nav_labels == EXPECTED_NAV_LABELS,
                f"{rel}: nav labels must be {EXPECTED_NAV_LABELS}, got {parser.nav_labels}",
            )
        for attr, link in parser.links:
            parsed = urlparse(link)
            if parsed.scheme or parsed.path.startswith("mailto:"):
                continue
            if parsed.path:
                target = (path.parent / parsed.path).resolve()
            else:
                target = path.resolve()
            if not str(target).startswith(str(v.root)):
                v.error(f"{rel}: {attr} points outside project: {link}")
                continue
            if not target.exists():
                v.error(f"{rel}: broken local {attr}: {link}")
                continue
            if parsed.fragment:
                content = target.read_text(encoding="utf-8", errors="ignore")
                fragment = re.escape(parsed.fragment)
                if not re.search(rf'\bid=["\']{fragment}["\']', content):
                    v.error(f"{rel}: missing anchor #{parsed.fragment} in {target.relative_to(v.root)}")


def check_forbidden_advice(v: Validator) -> None:
    scan_files = [
        *Path(v.root / "app").glob("*.html"),
        *Path(v.root / "reports/daily").glob("*"),
        *Path(v.root / "agents").glob("**/AGENTS.md"),
        v.root / "data/sample/report_judge.json",
        v.root / "data/sample/agent_outputs.json",
    ]
    allowed_context = [
        "出さない",
        "提案しない",
        "しない",
        "禁止",
        "ではなく",
        "出力せず",
    ]
    for path in scan_files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_ADVICE_PATTERNS:
            for match in re.finditer(pattern, text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end]
                if any(token in line for token in allowed_context):
                    continue
                line_no = text.count("\n", 0, match.start()) + 1
                v.error(f"{path.relative_to(v.root)}:{line_no}: forbidden advice phrase '{match.group(0)}'")


def run_generator(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def check_generated_freshness(v: Validator) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        report_out = tmp_path / "reports"
        report_cmd = [sys.executable, "scripts/generate_reports.py", "--out-dir", str(report_out)]
        report_result = run_generator(report_cmd, v.root)
        if report_result.returncode != 0:
            v.error(f"generate_reports.py failed: {report_result.stderr.strip() or report_result.stdout.strip()}")
        else:
            for generated in report_out.iterdir():
                current = v.root / "reports/daily" / generated.name
                if not current.exists():
                    v.error(f"generated report missing from reports/daily: {generated.name}")
                elif current.read_text(encoding="utf-8") != generated.read_text(encoding="utf-8"):
                    v.error(f"generated report is stale: {current.relative_to(v.root)}")

        app_out = tmp_path / "app"
        app_cmd = [sys.executable, "scripts/generate_app_pages.py", "--out-dir", str(app_out)]
        app_result = run_generator(app_cmd, v.root)
        if app_result.returncode != 0:
            v.error(f"generate_app_pages.py failed: {app_result.stderr.strip() or app_result.stdout.strip()}")
        else:
            for generated in app_out.glob("*.html"):
                current = v.root / "app" / generated.name
                if not current.exists():
                    v.error(f"generated app page missing from app/: {generated.name}")
                elif current.read_text(encoding="utf-8") != generated.read_text(encoding="utf-8"):
                    v.error(f"generated app page is stale: {current.relative_to(v.root)}")


def run_all_checks(check_generated: bool) -> int:
    v = Validator(ROOT)
    check_required_files(v)
    check_flow_docs(v)
    check_contract_schemas(v)
    check_config_examples(v)
    check_python_syntax(v)

    evidence = load_json(ROOT / "data/sample/evidence.json")
    agents = load_json(ROOT / "data/sample/agent_outputs.json")
    judge = load_json(ROOT / "data/sample/report_judge.json")
    health = load_json(ROOT / "data/sample/health.json")
    config = load_json(ROOT / "config/app.example.json")

    evidence_ids = check_evidence(v, evidence)
    check_agents(v, agents, evidence_ids)
    check_judge(v, judge, evidence_ids)
    agent_outputs = agents.get("agent_outputs", []) if isinstance(agents, dict) else []
    check_health(v, health, len(evidence) if isinstance(evidence, list) else 0, len(agent_outputs) if isinstance(agent_outputs, list) else 0)
    check_config(v, config)
    script_ids = check_flow_scripts(v)
    check_auto_search(v, script_ids)
    check_html_links(v)
    check_forbidden_advice(v)
    if check_generated:
        check_generated_freshness(v)
    return v.print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run static maintenance checks.")
    parser.add_argument(
        "--skip-generated",
        action="store_true",
        help="Skip regenerated artifact comparisons.",
    )
    args = parser.parse_args()
    raise SystemExit(run_all_checks(check_generated=not args.skip_generated))


if __name__ == "__main__":
    main()
