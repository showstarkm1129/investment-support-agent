#!/usr/bin/env python3
"""Run an AgentTeam readout through an LLM provider and validate artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator as JsonSchemaValidator
except ImportError:
    from jsonschema import Draft7Validator as JsonSchemaValidator

from build_agent_team_readout import build_outputs
from run_flow import API_ENV_KEYS, call_api_provider, configured_env_file, load_env_file


ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
ANALYSIS_AGENTS = {"bull", "bear", "contradiction", "pricing"}
PROVIDERS = ("mock", "codex_cli", "openai_api", "anthropic_api", "gemini_api")


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def provider_text(response: dict[str, Any], provider: str) -> str:
    if provider == "openai_api":
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        chunks: list[str] = []
        for output in response.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    if provider == "anthropic_api":
        chunks = []
        for content in response.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
        return "\n".join(chunks)

    if provider == "gemini_api":
        chunks = []
        for candidate in response.get("candidates", []):
            content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
            for part in content.get("parts", []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunks)

    raise ValueError(f"Unsupported response provider: {provider}")


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        start = match.start()
        try:
            value, end = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return stripped[start : start + end]
    raise ValueError("LLM response did not contain a JSON object")


def parse_llm_payload(text: str) -> dict[str, Any]:
    payload = json.loads(extract_json_text(text))
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON response must be an object")
    return payload


def build_prompt(
    *,
    evidence: list[dict[str, Any]],
    baseline_agents: dict[str, Any],
    baseline_judge: dict[str, Any],
    target: dict[str, Any],
) -> str:
    return f"""You are running an investment-support AgentTeam.

Return exactly one JSON object with these top-level keys:
- agent_outputs
- report_judge

Rules:
- agent_outputs must follow system/contracts/agent_output.schema.json.
- report_judge must follow system/contracts/report_judge.schema.json.
- Use only evidence IDs present in the Evidence input.
- Keep uncertainty explicit.
- Do not give trading instructions.
- Do not include markdown fences or commentary.

Target:
{compact_json(target)}

Evidence input:
{compact_json(evidence)}

Deterministic baseline to improve, keep schema-compatible:
{compact_json({"agent_outputs": baseline_agents, "report_judge": baseline_judge})}
"""


def build_repair_prompt(*, original_prompt: str, error: str, previous_text: str) -> str:
    return f"""{original_prompt}

The previous response failed validation.

Validation error:
{error}

Previous response:
{previous_text[:12000]}

Return a corrected JSON object only. Do not include markdown fences or commentary.
"""


def validate_schema(schema_path: Path, payload: Any) -> None:
    schema = load_json(schema_path)
    JsonSchemaValidator(schema).validate(payload)


def validate_references(agent_outputs: dict[str, Any], report_judge: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    evidence_ids = {item.get("evidence_id") for item in evidence if isinstance(item, dict)}
    seen_agents = {item.get("agent_name") for item in agent_outputs.get("agent_outputs", [])}
    missing_agents = ANALYSIS_AGENTS - seen_agents
    if missing_agents:
        raise ValueError(f"agent_outputs missing required agent(s): {sorted(missing_agents)}")

    for item in agent_outputs.get("agent_outputs", []):
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                raise ValueError(f"{item.get('agent_name')}.evidence_ids contains unknown evidence_id: {evidence_id}")

    for item in report_judge.get("used_evidence", []):
        evidence_id = item.get("evidence_id")
        if evidence_id not in evidence_ids:
            raise ValueError(f"report_judge.used_evidence contains unknown evidence_id: {evidence_id}")

    for item in report_judge.get("view_change_conditions", []):
        for evidence_id in item.get("related_evidence_ids", []):
            if evidence_id not in evidence_ids:
                raise ValueError(f"report_judge.view_change_conditions contains unknown evidence_id: {evidence_id}")


def validate_payload(payload: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    agent_outputs = payload.get("agent_outputs")
    report_judge = payload.get("report_judge")
    if not isinstance(agent_outputs, dict) or not isinstance(report_judge, dict):
        raise ValueError("LLM payload must contain object keys: agent_outputs, report_judge")

    validate_schema(ROOT / "system" / "contracts" / "agent_output.schema.json", agent_outputs)
    validate_schema(ROOT / "system" / "contracts" / "report_judge.schema.json", report_judge)
    validate_references(agent_outputs, report_judge, evidence)
    return agent_outputs, report_judge


def apply_low_confidence_hold(report_judge: dict[str, Any]) -> None:
    market = report_judge.get("market_readout", {})
    if not isinstance(market, dict) or market.get("confidence") != "low":
        return
    report_judge["decision_stage"] = "draft"
    warnings = report_judge.setdefault("warnings", [])
    if isinstance(warnings, list) and "low_confidence_hold" not in warnings:
        warnings.append("low_confidence_hold")


def secret_values(keys: list[str]) -> list[str]:
    values = []
    for key in keys:
        value = os.environ.get(key)
        if value and len(value) >= 8:
            values.append(value)
    return values


def assert_no_secret_leak(paths: list[Path], secrets: list[str]) -> None:
    if not secrets:
        return
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for secret in secrets:
            if secret in text:
                raise RuntimeError(f"secret value leaked into artifact: {path}")


def mock_payload(baseline_agents: dict[str, Any], baseline_judge: dict[str, Any]) -> dict[str, Any]:
    return {"agent_outputs": baseline_agents, "report_judge": baseline_judge}


def call_codex_cli(*, model: str, reasoning_effort: str, prompt: str, timeout: int) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as prompt_file:
        prompt_file.write(prompt)
        prompt_path = Path(prompt_file.name)
    command = [
        "codex",
        "exec",
        "-m",
        model,
        "-c",
        f"model_reasoning_effort={reasoning_effort}",
        "--ignore-user-config",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--dangerously-bypass-approvals-and-sandbox",
        f"Read {prompt_path} and return only the requested JSON object.",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "provider": "codex_cli",
            "command": command[:7] + ["...", command[-1]],
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    finally:
        try:
            prompt_path.unlink()
        except OSError:
            pass


def call_provider(
    *,
    provider: str,
    model: str,
    prompt: str,
    baseline_agents: dict[str, Any],
    baseline_judge: dict[str, Any],
    codex_reasoning_effort: str,
    codex_timeout: int,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if provider == "mock":
        payload = mock_payload(baseline_agents, baseline_judge)
        return payload, json.dumps(payload, ensure_ascii=False), {"provider": "mock", "response_kind": "deterministic_baseline"}

    if provider == "codex_cli":
        raw_response = call_codex_cli(model=model, reasoning_effort=codex_reasoning_effort, prompt=prompt, timeout=codex_timeout)
        text = str(raw_response.get("stdout") or "")
        if raw_response.get("returncode") != 0:
            raise RuntimeError(f"codex_cli failed with returncode {raw_response.get('returncode')}: {raw_response.get('stderr', '')[:2000]}")
        payload = parse_llm_payload(text)
        return payload, text, raw_response

    raw_response = call_api_provider(provider, model, prompt)
    text = provider_text(raw_response, provider)
    payload = parse_llm_payload(text)
    return payload, text, raw_response


def health_payload(
    *,
    run_id: str,
    target_id: str,
    status: str,
    summary: str,
    checks: list[dict[str, Any]],
    evidence_count: int,
    agent_success: int,
    agent_failed: int,
    report_outputs: int,
) -> dict[str, Any]:
    return {
        "schema_version": "health_snapshot_v1",
        "run_id": run_id,
        "run_at": now_jst(),
        "target_id": target_id,
        "overall_status": status,
        "summary": summary,
        "stats": {
            "evidence_total": evidence_count,
            "agent_success": agent_success,
            "agent_failed": agent_failed,
            "report_outputs": report_outputs,
        },
        "sections": [
            {
                "section_id": "agentteam_llm",
                "title": "AgentTeam LLM",
                "checks": checks,
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgentTeam readout through an LLM provider.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--report-date")
    parser.add_argument("--run-id")
    parser.add_argument("--provider", choices=PROVIDERS, default="codex_cli")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--codex-reasoning-effort", default="low")
    parser.add_argument("--codex-timeout", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--save-prompt", action="store_true")
    parser.add_argument("--save-raw-response", action="store_true")
    args = parser.parse_args()

    env_file = args.env_file or configured_env_file()
    loaded_env_keys = load_env_file(env_file)
    required_key = API_ENV_KEYS.get(args.provider)
    if required_key and not os.environ.get(required_key):
        raise RuntimeError(f"{required_key} is not set")

    evidence = load_json(args.evidence)
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("--evidence must contain a non-empty Evidence JSON array")

    first_identity = evidence[0].get("identity", {})
    report_date = args.report_date or str(first_identity.get("published_at", ""))[:10]
    if not report_date:
        raise ValueError("--report-date is required when evidence has no published_at")
    run_id = args.run_id or f"LLM-{report_date.replace('-', '')}-{args.stock_code}"
    run_at = now_jst()
    target = {
        "target_id": args.target_id,
        "target_type": "stock",
        "stock_code": args.stock_code,
        "company_name": args.company_name,
        "market": args.market,
        "themes": args.theme,
    }

    baseline_agents, baseline_judge = build_outputs(
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
    args.out_dir.mkdir(parents=True, exist_ok=True)
    agents_path = args.out_dir / "agent_outputs.json"
    judge_path = args.out_dir / "report_judge.json"
    manifest_path = args.out_dir / "llm_run_manifest.json"
    prompt_path = args.out_dir / "llm_prompt.md"
    raw_path = args.out_dir / "llm_raw_response.json"
    failures_dir = args.out_dir / "llm_failures"
    health_path = args.out_dir / "health.json"

    prompt = build_prompt(evidence=evidence, baseline_agents=baseline_agents, baseline_judge=baseline_judge, target=target)
    attempt_prompt = prompt
    failures: list[dict[str, Any]] = []
    raw_response: dict[str, Any] = {}
    agent_outputs: dict[str, Any] | None = None
    report_judge: dict[str, Any] | None = None

    for attempt in range(1, max(args.max_attempts, 1) + 1):
        raw_text = ""
        try:
            llm_payload, raw_text, raw_response = call_provider(
                provider=args.provider,
                model=args.model,
                prompt=attempt_prompt,
                baseline_agents=baseline_agents,
                baseline_judge=baseline_judge,
                codex_reasoning_effort=args.codex_reasoning_effort,
                codex_timeout=args.codex_timeout,
            )
            agent_outputs, report_judge = validate_payload(llm_payload, evidence)
            apply_low_confidence_hold(report_judge)
            break
        except Exception as exc:
            failure = {
                "schema_version": "agent_team_llm_failure_v1",
                "attempt": attempt,
                "failed_at": now_jst(),
                "provider": args.provider,
                "model": args.model,
                "error": str(exc),
                "raw_text_excerpt": raw_text[:12000],
            }
            failures.append(failure)
            failures_dir.mkdir(parents=True, exist_ok=True)
            write_json(failures_dir / f"attempt_{attempt:02d}.json", failure)
            attempt_prompt = build_repair_prompt(original_prompt=prompt, error=str(exc), previous_text=raw_text)

    if agent_outputs is None or report_judge is None:
        error_path = args.out_dir / "agent_team_error.json"
        write_json(
            error_path,
            {
                "schema_version": "agent_team_error_v1",
                "run_id": run_id,
                "run_at": run_at,
                "provider": args.provider,
                "model": args.model,
                "failures": failures,
            },
        )
        write_json(
            health_path,
            health_payload(
                run_id=run_id,
                target_id=args.target_id,
                status="error",
                summary="AgentTeam LLM failed; see agent_team_error.json and llm_failures/.",
                checks=[
                    {
                        "check_id": "llm_validation",
                        "label": "LLM output validation",
                        "status": "error",
                        "message": failures[-1]["error"] if failures else "unknown error",
                        "detail": str(error_path),
                        "last_run_at": now_jst(),
                    }
                ],
                evidence_count=len(evidence),
                agent_success=0,
                agent_failed=1,
                report_outputs=0,
            ),
        )
        raise RuntimeError(f"AgentTeam LLM failed; see {error_path}")

    write_json(agents_path, agent_outputs)
    write_json(judge_path, report_judge)
    write_json(
        health_path,
        health_payload(
            run_id=run_id,
            target_id=args.target_id,
            status="ok",
            summary="AgentTeam LLM artifacts passed schema and Evidence ID validation.",
            checks=[
                {
                    "check_id": "llm_validation",
                    "label": "LLM output validation",
                    "status": "ok",
                    "message": f"Validated after {len(failures) + 1} attempt(s).",
                    "detail": "agent_outputs.json and report_judge.json were written.",
                    "last_run_at": now_jst(),
                },
                {
                    "check_id": "low_confidence_hold",
                    "label": "Low confidence hold",
                    "status": "warn" if "low_confidence_hold" in report_judge.get("warnings", []) else "ok",
                    "message": "Low confidence output was held as draft." if "low_confidence_hold" in report_judge.get("warnings", []) else "No low-confidence hold required.",
                    "detail": "decision_stage remains draft for generated readouts.",
                    "last_run_at": now_jst(),
                },
            ],
            evidence_count=len(evidence),
            agent_success=4,
            agent_failed=0,
            report_outputs=0,
        ),
    )
    manifest = {
        "schema_version": "agent_team_llm_run_v1",
        "run_id": run_id,
        "run_at": run_at,
        "provider": args.provider,
        "model": args.model,
        "codex_reasoning_effort": args.codex_reasoning_effort if args.provider == "codex_cli" else None,
        "max_attempts": max(args.max_attempts, 1),
        "attempts_used": len(failures) + 1,
        "failure_count": len(failures),
        "evidence_path": str(args.evidence),
        "agent_outputs_path": str(agents_path),
        "report_judge_path": str(judge_path),
        "health_path": str(health_path),
        "loaded_env_keys": sorted(loaded_env_keys),
        "required_env_key": required_key,
        "prompt_saved": bool(args.save_prompt),
        "raw_response_saved": bool(args.save_raw_response),
    }
    write_json(manifest_path, manifest)
    if args.save_prompt:
        prompt_path.write_text(prompt, encoding="utf-8")
    if args.save_raw_response:
        write_json(raw_path, raw_response)

    leak_paths = [agents_path, judge_path, manifest_path]
    if args.save_prompt:
        leak_paths.append(prompt_path)
    if args.save_raw_response:
        leak_paths.append(raw_path)
    assert_no_secret_leak(leak_paths, secret_values(loaded_env_keys + ([required_key] if required_key else [])))

    print(f"agent_outputs_path={agents_path}")
    print(f"report_judge_path={judge_path}")
    print(f"manifest_path={manifest_path}")
    print(f"health_path={health_path}")
    print(f"provider={args.provider}")
    print(f"model={args.model}")
    print(f"loaded_env_keys={sorted(loaded_env_keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
