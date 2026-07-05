#!/usr/bin/env python3
"""Run the Agent chain step by step, passing prior outputs to later Agents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator as JsonSchemaValidator
except ImportError:
    from jsonschema import Draft7Validator as JsonSchemaValidator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from build_agent_team_readout import build_outputs  # noqa: E402
from run_agent_team_llm import (  # noqa: E402
    apply_low_confidence_hold,
    assert_no_secret_leak,
    build_repair_prompt,
    call_codex_cli,
    load_json,
    now_jst,
    parse_llm_payload,
    secret_values,
)
from run_flow import API_ENV_KEYS, call_api_provider, configured_env_file, load_env_file  # noqa: E402


ANALYSIS_AGENTS = ["bull", "bear", "contradiction", "pricing"]
ALL_AGENT_STEPS = ["search_design", "evidence_builder", *ANALYSIS_AGENTS, "report_judge"]
PROVIDERS = ("mock", "codex_cli", "openai_api", "anthropic_api", "gemini_api")
CONTRACTS = ROOT / "system" / "contracts"
AGENT_DOCS = ROOT / "system" / "agents"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def load_agent_doc(agent_id: str) -> str:
    return (AGENT_DOCS / agent_id / "AGENTS.md").read_text(encoding="utf-8")


def validate_contract(schema_name: str, payload: Any) -> None:
    schema = load_json(CONTRACTS / schema_name)
    JsonSchemaValidator(schema).validate(payload)


def evidence_ids(evidence: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("evidence_id")) for item in evidence if isinstance(item, dict)}


def validate_referenced_evidence(refs: list[str], evidence: list[dict[str, Any]], path: str) -> None:
    known = evidence_ids(evidence)
    for ref in refs:
        if ref not in known:
            raise ValueError(f"{path}: unknown evidence_id {ref}")


def validate_research_plan(plan: dict[str, Any]) -> None:
    required = ["schema_version", "agent_name", "research_questions", "required_sources", "fetch_modules", "priority", "expected_evidence_types", "stop_conditions", "health_notes"]
    for key in required:
        if key not in plan:
            raise ValueError(f"research_plan missing key: {key}")
    if plan["schema_version"] != "research_plan_v1":
        raise ValueError("research_plan schema_version must be research_plan_v1")
    if plan["agent_name"] != "search_design":
        raise ValueError("research_plan agent_name must be search_design")
    for key in required[2:]:
        if not isinstance(plan[key], list):
            raise ValueError(f"research_plan.{key} must be a list")


def validate_agent_output(item: dict[str, Any], *, agent_name: str, evidence: list[dict[str, Any]]) -> None:
    bundle = {
        "schema_version": "agent_outputs_bundle_v1",
        "target_id": evidence[0]["identity"]["target_id"],
        "report_date": evidence[0]["identity"]["published_at"][:10],
        "agent_outputs": [item],
    }
    validate_contract("agent_output.schema.json", bundle)
    if item.get("agent_name") != agent_name:
        raise ValueError(f"agent output agent_name must be {agent_name}")
    validate_referenced_evidence(item.get("evidence_ids", []), evidence, f"{agent_name}.evidence_ids")


def validate_agent_bundle(bundle: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    validate_contract("agent_output.schema.json", bundle)
    seen = [item.get("agent_name") for item in bundle.get("agent_outputs", [])]
    if seen != ANALYSIS_AGENTS:
        raise ValueError(f"agent bundle must be ordered {ANALYSIS_AGENTS}, got {seen}")
    for item in bundle["agent_outputs"]:
        validate_referenced_evidence(item.get("evidence_ids", []), evidence, f"{item.get('agent_name')}.evidence_ids")


def validate_report_judge(report: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    validate_contract("report_judge.schema.json", report)
    for item in report.get("used_evidence", []):
        validate_referenced_evidence([item.get("evidence_id")], evidence, "report_judge.used_evidence")
    for item in report.get("view_change_conditions", []):
        validate_referenced_evidence(item.get("related_evidence_ids", []), evidence, "report_judge.view_change_conditions")


def validate_step_payload(
    *,
    step: str,
    payload: dict[str, Any],
    evidence: list[dict[str, Any]],
    research_plan: dict[str, Any] | None,
    agent_outputs: list[dict[str, Any]],
) -> None:
    if step == "search_design":
        validate_research_plan(payload)
        return
    if step == "evidence_builder":
        if payload.get("schema_version") != "evidence_builder_review_v1":
            raise ValueError("evidence_builder schema_version must be evidence_builder_review_v1")
        if payload.get("agent_name") != "evidence_builder":
            raise ValueError("evidence_builder agent_name must be evidence_builder")
        if isinstance(payload.get("evidence"), list):
            validate_contract("evidence.schema.json", payload["evidence"])
            return
        accepted_ids = payload.get("accepted_evidence_ids")
        if not isinstance(accepted_ids, list):
            raise ValueError("evidence_builder output must contain evidence array or accepted_evidence_ids array")
        validate_referenced_evidence([str(item) for item in accepted_ids], evidence, "evidence_builder.accepted_evidence_ids")
        return
    if step in ANALYSIS_AGENTS:
        validate_agent_output(payload, agent_name=step, evidence=evidence)
        return
    validate_report_judge(payload, evidence)


def provider_text(response: dict[str, Any], provider: str) -> str:
    if provider == "openai_api":
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        chunks = []
        for output in response.get("output", []):
            if isinstance(output, dict):
                for content in output.get("content", []):
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        chunks.append(content["text"])
        return "\n".join(chunks)
    if provider == "anthropic_api":
        return "\n".join(content["text"] for content in response.get("content", []) if isinstance(content, dict) and isinstance(content.get("text"), str))
    if provider == "gemini_api":
        chunks = []
        for candidate in response.get("candidates", []):
            if isinstance(candidate, dict):
                for part in candidate.get("content", {}).get("parts", []):
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
        return "\n".join(chunks)
    raise ValueError(f"Unsupported provider text extraction: {provider}")


def target_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "target_id": args.target_id,
        "target_type": "stock",
        "stock_code": args.stock_code,
        "company_name": args.company_name,
        "market": args.market,
        "themes": args.theme,
    }


def baseline_outputs(evidence: list[dict[str, Any]], args: argparse.Namespace, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_outputs(
        evidence,
        target_id=args.target_id,
        stock_code=args.stock_code,
        company_name=args.company_name,
        market=args.market,
        themes=args.theme,
        report_date=args.report_date,
        run_id=run_id,
        run_at=now_jst(),
    )


def mock_research_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "research_plan_v1",
        "agent_name": "search_design",
        "research_questions": [
            f"{args.company_name}の価格・出来高変化は何を示すか",
            "EDINET/IR/ニュースで価格反応の背景を確認できるか",
            "同業・指数比較で個別要因と市場要因を切り分けられるか",
        ],
        "required_sources": ["jquants", "edinet", "ir", "news", "sector_index"],
        "fetch_modules": ["connectors/jquants", "connectors/edinet", "connectors/ir", "connectors/news"],
        "priority": ["price_volume", "disclosure_edinet", "ir", "news"],
        "expected_evidence_types": ["price_volume", "disclosure_edinet", "ir", "news"],
        "stop_conditions": ["Evidenceが0件の場合は低信頼で保留", "Evidence ID不整合があれば失敗"],
        "health_notes": ["EDINET該当なしはwarnとして記録", "ニュース/IR未接続はmissing_informationへ回す"],
    }


def prompt_for_step(
    *,
    step: str,
    args: argparse.Namespace,
    evidence: list[dict[str, Any]],
    research_plan: dict[str, Any] | None,
    agent_outputs: list[dict[str, Any]],
    baseline_agents: dict[str, Any],
    baseline_judge: dict[str, Any],
) -> str:
    target = target_from_args(args)
    common = f"""Target:
{compact_json(target)}

Evidence:
{compact_json(evidence)}

Rules:
- Return exactly one JSON object.
- Do not include markdown fences or commentary.
- Use only Evidence IDs present in the Evidence input.
- Do not give trading instructions.
"""
    if step == "search_design":
        return f"""{load_agent_doc(step)}

{common}

Return a research_plan_v1 JSON object with keys:
schema_version, agent_name, research_questions, required_sources, fetch_modules,
priority, expected_evidence_types, stop_conditions, health_notes.
"""
    if step == "evidence_builder":
        return f"""{load_agent_doc(step)}

{common}

Research plan:
{compact_json(research_plan)}

Connector-built Evidence is already supplied. Review it for schema-compatible use.
Connector-built Evidence is already schema-validated. Do not rewrite the full Evidence array.
Return exactly:
{{"schema_version":"evidence_builder_review_v1","agent_name":"evidence_builder","accepted_evidence_ids":["E..."],"notes":["..."]}}
where accepted_evidence_ids contains only Evidence IDs present in the Evidence input.
"""
    if step in ANALYSIS_AGENTS:
        baseline_item = next(item for item in baseline_agents["agent_outputs"] if item["agent_name"] == step)
        return f"""{load_agent_doc(step)}

{common}

Research plan:
{compact_json(research_plan)}

Previous analysis agent outputs:
{compact_json(agent_outputs)}

Baseline for this agent:
{compact_json(baseline_item)}

Return exactly one agent_output_v1 JSON object for agent_name "{step}".
It must match one item of system/contracts/agent_output.schema.json.
"""
    return f"""{load_agent_doc(step)}

{common}

Research plan:
{compact_json(research_plan)}

Analysis agent outputs, in order:
{compact_json(agent_outputs)}

Baseline report_judge:
{compact_json(baseline_judge)}

Return exactly one report_readout_v1 JSON object matching system/contracts/report_judge.schema.json.
"""


def call_step_provider(
    *,
    provider: str,
    model: str,
    prompt: str,
    codex_reasoning_effort: str,
    codex_timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if provider == "codex_cli":
        raw = call_codex_cli(model=model, reasoning_effort=codex_reasoning_effort, prompt=prompt, timeout=codex_timeout)
        text = str(raw.get("stdout") or "")
        if raw.get("returncode") != 0:
            raise RuntimeError(f"codex_cli failed with returncode {raw.get('returncode')}: {raw.get('stderr', '')[:2000]}")
        return parse_llm_payload(text), raw, text
    raw = call_api_provider(provider, model, prompt)
    text = provider_text(raw, provider)
    return parse_llm_payload(text), raw, text


def run_step(
    *,
    step: str,
    args: argparse.Namespace,
    output_dir: Path,
    evidence: list[dict[str, Any]],
    research_plan: dict[str, Any] | None,
    agent_outputs: list[dict[str, Any]],
    baseline_agents: dict[str, Any],
    baseline_judge: dict[str, Any],
) -> dict[str, Any]:
    step_dir = output_dir / "agent_steps"
    step_dir.mkdir(parents=True, exist_ok=True)
    prompt = prompt_for_step(
        step=step,
        args=args,
        evidence=evidence,
        research_plan=research_plan,
        agent_outputs=agent_outputs,
        baseline_agents=baseline_agents,
        baseline_judge=baseline_judge,
    )
    if args.save_prompts:
        (step_dir / f"{step}_prompt.md").write_text(prompt, encoding="utf-8")

    if args.provider == "mock":
        if step == "search_design":
            payload = mock_research_plan(args)
        elif step == "evidence_builder":
            payload = {
                "schema_version": "evidence_builder_review_v1",
                "agent_name": "evidence_builder",
                "accepted_evidence_ids": sorted(evidence_ids(evidence)),
                "notes": ["Connector-built Evidence accepted without rewriting full payload."],
            }
        elif step in ANALYSIS_AGENTS:
            payload = next(item for item in baseline_agents["agent_outputs"] if item["agent_name"] == step)
        else:
            payload = baseline_judge
        validate_step_payload(step=step, payload=payload, evidence=evidence, research_plan=research_plan, agent_outputs=agent_outputs)
        write_json(step_dir / f"{step}.json", payload)
        return payload

    attempt_prompt = prompt
    failures = []
    for attempt in range(1, max(args.max_attempts, 1) + 1):
        raw_text = ""
        try:
            payload, raw_response, raw_text = call_step_provider(
                provider=args.provider,
                model=args.model,
                prompt=attempt_prompt,
                codex_reasoning_effort=args.codex_reasoning_effort,
                codex_timeout=args.codex_timeout,
            )
            if args.save_raw_responses:
                write_json(step_dir / f"{step}_raw_response_attempt_{attempt:02d}.json", raw_response)
            validate_step_payload(step=step, payload=payload, evidence=evidence, research_plan=research_plan, agent_outputs=agent_outputs)
            write_json(step_dir / f"{step}.json", payload)
            return payload
        except Exception as exc:
            failure = {
                "schema_version": "agent_step_failure_v1",
                "agent_name": step,
                "attempt": attempt,
                "failed_at": now_jst(),
                "error": str(exc),
                "raw_text_excerpt": raw_text[:12000],
            }
            failures.append(failure)
            write_json(step_dir / f"{step}_failure_attempt_{attempt:02d}.json", failure)
            attempt_prompt = build_repair_prompt(original_prompt=prompt, error=str(exc), previous_text=raw_text)
    raise RuntimeError(f"{step} failed after {len(failures)} attempt(s): {failures[-1]['error'] if failures else 'unknown error'}")


def run_or_resume_step(
    *,
    step: str,
    args: argparse.Namespace,
    output_dir: Path,
    evidence: list[dict[str, Any]],
    research_plan: dict[str, Any] | None,
    agent_outputs: list[dict[str, Any]],
    baseline_agents: dict[str, Any],
    baseline_judge: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    step_path = output_dir / "agent_steps" / f"{step}.json"
    if args.resume and step_path.is_file():
        payload = load_json(step_path)
        if not isinstance(payload, dict):
            raise ValueError(f"{step_path} must contain a JSON object")
        validate_step_payload(
            step=step,
            payload=payload,
            evidence=evidence,
            research_plan=research_plan,
            agent_outputs=agent_outputs,
        )
        return payload, True
    payload = run_step(
        step=step,
        args=args,
        output_dir=output_dir,
        evidence=evidence,
        research_plan=research_plan,
        agent_outputs=agent_outputs,
        baseline_agents=baseline_agents,
        baseline_judge=baseline_judge,
    )
    return payload, False


def health_payload(*, args: argparse.Namespace, run_id: str, status: str, checks: list[dict[str, Any]], evidence_count: int, agent_failed: int) -> dict[str, Any]:
    return {
        "schema_version": "health_snapshot_v1",
        "run_id": run_id,
        "run_at": now_jst(),
        "target_id": args.target_id,
        "overall_status": status,
        "summary": "Sequential Agent chain completed." if status == "ok" else "Sequential Agent chain failed.",
        "stats": {
            "evidence_total": evidence_count,
            "agent_success": 7 - agent_failed,
            "agent_failed": agent_failed,
            "report_outputs": 0,
        },
        "sections": [{"section_id": "agent_sequence", "title": "Sequential Agent Chain", "checks": checks}],
    }


def check(check_id: str, label: str, status: str, message: str, detail: str = "") -> dict[str, Any]:
    return {
        "check_id": check_id,
        "label": label,
        "status": status,
        "message": message,
        "detail": detail,
        "last_run_at": now_jst(),
    }


def initial_step_states(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        step: {
            "agent_name": step,
            "status": "pending",
            "updated_at": None,
            "artifact_path": str(output_dir / "agent_steps" / f"{step}.json"),
        }
        for step in ALL_AGENT_STEPS
    }


def write_sequence_status(
    *,
    path: Path,
    args: argparse.Namespace,
    run_id: str,
    status: str,
    current_step: str | None,
    step_states: dict[str, dict[str, Any]],
    resumed_steps: list[str],
    completed_steps: list[str],
    failed_step: str | None = None,
    error: str = "",
) -> None:
    write_json(
        path,
        {
            "schema_version": "agent_sequence_status_v1",
            "run_id": run_id,
            "updated_at": now_jst(),
            "target_id": args.target_id,
            "provider": args.provider,
            "model": args.model,
            "status": status,
            "current_step": current_step,
            "failed_step": failed_step,
            "completed_steps": completed_steps,
            "resumed_steps": resumed_steps,
            "steps": [step_states[step] for step in ALL_AGENT_STEPS],
            "error": error,
        },
    )


def run_sequence(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.out_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    health_path = output_dir / "health.json"
    sequence_health_path = output_dir / "agent_sequence_health.json"
    sequence_status_path = output_dir / "agent_sequence_status.json"
    run_id = args.run_id or f"SEQ-{args.report_date.replace('-', '')}-{args.stock_code}"
    loaded_keys = load_env_file(args.env_file or configured_env_file())
    required_key = API_ENV_KEYS.get(args.provider)
    if required_key and not os.environ.get(required_key):
        raise RuntimeError(f"{required_key} is not set")

    evidence = load_json(args.evidence)
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("--evidence must contain a non-empty Evidence JSON array")
    validate_contract("evidence.schema.json", evidence)

    baseline_agents, baseline_judge = baseline_outputs(evidence, args, run_id)
    checks = [check("evidence_input", "Evidence input", "ok", f"{len(evidence)} Evidence item(s) loaded.", str(args.evidence))]
    research_plan: dict[str, Any] | None = None
    agent_outputs: list[dict[str, Any]] = []
    resumed_steps: list[str] = []
    completed_steps: list[str] = []
    step_states = initial_step_states(output_dir)
    write_sequence_status(
        path=sequence_status_path,
        args=args,
        run_id=run_id,
        status="running",
        current_step=None,
        step_states=step_states,
        resumed_steps=resumed_steps,
        completed_steps=completed_steps,
    )

    try:
        step_states["search_design"]["status"] = "in_progress"
        step_states["search_design"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step="search_design", step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        research_plan, resumed = run_or_resume_step(
            step="search_design",
            args=args,
            output_dir=output_dir,
            evidence=evidence,
            research_plan=None,
            agent_outputs=[],
            baseline_agents=baseline_agents,
            baseline_judge=baseline_judge,
        )
        if resumed:
            resumed_steps.append("search_design")
        completed_steps.append("search_design")
        step_states["search_design"]["status"] = "resumed" if resumed else "ok"
        step_states["search_design"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        validate_research_plan(research_plan)
        checks.append(check("search_design", "Search Design", "skipped" if resumed else "ok", "Research plan loaded from previous step output." if resumed else "Research plan validated."))

        step_states["evidence_builder"]["status"] = "in_progress"
        step_states["evidence_builder"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step="evidence_builder", step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        evidence_payload, resumed = run_or_resume_step(
            step="evidence_builder",
            args=args,
            output_dir=output_dir,
            evidence=evidence,
            research_plan=research_plan,
            agent_outputs=[],
            baseline_agents=baseline_agents,
            baseline_judge=baseline_judge,
        )
        if resumed:
            resumed_steps.append("evidence_builder")
        completed_steps.append("evidence_builder")
        step_states["evidence_builder"]["status"] = "resumed" if resumed else "ok"
        step_states["evidence_builder"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        if isinstance(evidence_payload.get("evidence"), list):
            evidence = evidence_payload["evidence"]
        else:
            accepted_ids = evidence_payload.get("accepted_evidence_ids")
            if not isinstance(accepted_ids, list):
                raise ValueError("evidence_builder output must contain evidence array or accepted_evidence_ids array")
            validate_referenced_evidence([str(item) for item in accepted_ids], evidence, "evidence_builder.accepted_evidence_ids")
        validate_contract("evidence.schema.json", evidence)
        write_json(output_dir / "evidence.json", evidence)
        checks.append(check("evidence_builder", "Evidence Builder", "skipped" if resumed else "ok", f"{len(evidence)} Evidence item(s) loaded from previous step output." if resumed else f"{len(evidence)} Evidence item(s) validated."))

        for agent_name in ANALYSIS_AGENTS:
            step_states[agent_name]["status"] = "in_progress"
            step_states[agent_name]["updated_at"] = now_jst()
            write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step=agent_name, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
            item, resumed = run_or_resume_step(
                step=agent_name,
                args=args,
                output_dir=output_dir,
                evidence=evidence,
                research_plan=research_plan,
                agent_outputs=agent_outputs,
                baseline_agents=baseline_agents,
                baseline_judge=baseline_judge,
            )
            if resumed:
                resumed_steps.append(agent_name)
            completed_steps.append(agent_name)
            step_states[agent_name]["status"] = "resumed" if resumed else "ok"
            step_states[agent_name]["updated_at"] = now_jst()
            write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
            validate_agent_output(item, agent_name=agent_name, evidence=evidence)
            agent_outputs.append(item)
            checks.append(check(agent_name, agent_name, "skipped" if resumed else "ok", "Agent output loaded from previous step output." if resumed else "Agent output validated."))

        bundle = {
            "schema_version": "agent_outputs_bundle_v1",
            "target_id": args.target_id,
            "report_date": args.report_date,
            "agent_outputs": agent_outputs,
        }
        validate_agent_bundle(bundle, evidence)
        write_json(output_dir / "agent_outputs.json", bundle)

        step_states["report_judge"]["status"] = "in_progress"
        step_states["report_judge"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step="report_judge", step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        report, resumed = run_or_resume_step(
            step="report_judge",
            args=args,
            output_dir=output_dir,
            evidence=evidence,
            research_plan=research_plan,
            agent_outputs=agent_outputs,
            baseline_agents=baseline_agents,
            baseline_judge=baseline_judge,
        )
        if resumed:
            resumed_steps.append("report_judge")
        completed_steps.append("report_judge")
        step_states["report_judge"]["status"] = "resumed" if resumed else "ok"
        step_states["report_judge"]["updated_at"] = now_jst()
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="running", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        apply_low_confidence_hold(report)
        validate_report_judge(report, evidence)
        write_json(output_dir / "report_judge.json", report)
        checks.append(check("report_judge", "Report Judge", "skipped" if resumed else "ok", "Report judge loaded from previous step output." if resumed else "Report judge output validated."))

        secret_paths = [output_dir / "evidence.json", output_dir / "agent_outputs.json", output_dir / "report_judge.json"]
        assert_no_secret_leak(secret_paths, secret_values(loaded_keys + ([required_key] if required_key else [])))
        checks.append(check("secret_leak", "Secret leak check", "ok", "No loaded secret value found in final artifacts."))

        health = health_payload(args=args, run_id=run_id, status="ok", checks=checks, evidence_count=len(evidence), agent_failed=0)
        write_json(health_path, health)
        write_json(sequence_health_path, health)
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="ok", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps)
        validate_contract("health.schema.json", health)
        manifest = {
            "schema_version": "agent_sequence_manifest_v1",
            "run_id": run_id,
            "run_at": now_jst(),
            "provider": args.provider,
            "model": args.model,
            "codex_reasoning_effort": args.codex_reasoning_effort if args.provider == "codex_cli" else None,
            "agent_order": ALL_AGENT_STEPS,
            "resume": bool(args.resume),
            "resumed_steps": resumed_steps,
            "status": "ok",
            "paths": {
                "evidence": str(output_dir / "evidence.json"),
                "agent_outputs": str(output_dir / "agent_outputs.json"),
                "report_judge": str(output_dir / "report_judge.json"),
                "health": str(health_path),
                "agent_sequence_health": str(sequence_health_path),
                "agent_sequence_status": str(sequence_status_path),
                "agent_steps_dir": str(output_dir / "agent_steps"),
            },
        }
        write_json(output_dir / "agent_sequence_manifest.json", manifest)
        return manifest
    except Exception as exc:
        failed_step = None
        for step in ALL_AGENT_STEPS:
            if step_states[step]["status"] == "in_progress":
                failed_step = step
                step_states[step]["status"] = "error"
                step_states[step]["updated_at"] = now_jst()
                break
        write_sequence_status(path=sequence_status_path, args=args, run_id=run_id, status="error", current_step=None, step_states=step_states, resumed_steps=resumed_steps, completed_steps=completed_steps, failed_step=failed_step, error=str(exc))
        checks.append(check("agent_sequence_error", "Agent sequence error", "error", str(exc)))
        health = health_payload(args=args, run_id=run_id, status="error", checks=checks, evidence_count=len(evidence), agent_failed=1)
        write_json(health_path, health)
        write_json(sequence_health_path, health)
        write_json(
            output_dir / "agent_sequence_manifest.json",
            {
                "schema_version": "agent_sequence_manifest_v1",
                "run_id": run_id,
                "run_at": now_jst(),
                "provider": args.provider,
                "model": args.model,
                "agent_order": ALL_AGENT_STEPS,
                "resume": bool(args.resume),
                "resumed_steps": resumed_steps,
                "status": "error",
                "error": str(exc),
                "paths": {
                    "health": str(health_path),
                    "agent_sequence_health": str(sequence_health_path),
                    "agent_sequence_status": str(sequence_status_path),
                    "agent_steps_dir": str(output_dir / "agent_steps"),
                },
            },
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run search_design -> evidence_builder -> analysis agents -> report_judge.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--run-id")
    parser.add_argument("--provider", choices=PROVIDERS, default="codex_cli")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--codex-reasoning-effort", default="low")
    parser.add_argument("--codex-timeout", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--save-prompts", action="store_true")
    parser.add_argument("--save-raw-responses", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse valid existing agent_steps/*.json and continue from the first missing step.")
    args = parser.parse_args()

    manifest = run_sequence(args)
    print(f"manifest_path={args.out_dir / 'agent_sequence_manifest.json'}")
    print(f"agent_steps_dir={args.out_dir / 'agent_steps'}")
    print(f"agent_outputs_path={manifest['paths']['agent_outputs']}")
    print(f"report_judge_path={manifest['paths']['report_judge']}")
    print(f"health_path={manifest['paths']['health']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
