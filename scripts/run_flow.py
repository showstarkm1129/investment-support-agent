#!/usr/bin/env python3
"""Create run folders and optional Agent Team command execution metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from prepare_agent_context import (
    FLOW_CHOICES,
    FLOW_AGENT_ORDER,
    FLOW_TO_BUCKET,
    ROOT,
    build_context,
    load_json,
    project_path,
    rel,
    write_context,
)


JST = timezone(timedelta(hours=9))
FLOW_SCRIPT_DIR = ROOT / "system" / "config" / "flow_scripts"
LOCAL_CONFIG_PATH = ROOT / "system" / "config" / "local.json"
PROVIDER_CHOICES = ("manual", "codex", "claude", "openai_api", "anthropic_api", "gemini_api")
MODE_CHOICES = ("prepare", "dry-run", "simulate", "live")
ANALYSIS_AGENTS = {"bull", "bear", "contradiction", "pricing"}
DEFAULT_MODELS = {
    "manual": "default",
    "codex": "default",
    "claude": "default",
    "openai_api": "gpt-5.1",
    "anthropic_api": "claude-sonnet-4-5",
    "gemini_api": "gemini-3-pro",
}
API_ENV_KEYS = {
    "openai_api": "OPENAI_API_KEY",
    "anthropic_api": "ANTHROPIC_API_KEY",
    "gemini_api": "GEMINI_API_KEY",
}

AGENT_DOC_PATHS = {
    "search_design": "system/agents/search_design/AGENTS.md",
    "evidence_builder": "system/agents/evidence_builder/AGENTS.md",
    "bull": "system/agents/bull/AGENTS.md",
    "bear": "system/agents/bear/AGENTS.md",
    "contradiction": "system/agents/contradiction/AGENTS.md",
    "pricing": "system/agents/pricing/AGENTS.md",
    "report_judge": "system/agents/report_judge/AGENTS.md",
    "chat_judge": "system/agents/chat_judge/AGENTS.md",
    "health": "system/contracts/health.schema.json",
    "generate_reports": "scripts/generate_reports.py",
    "generate_app_pages": "scripts/generate_app_pages.py",
}


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


def resolve_flow_script_path(reference: str) -> Path:
    path = Path(reference)
    if path.suffix:
        return project_path(path)
    return FLOW_SCRIPT_DIR / f"{reference}.json"


def load_flow_script(reference: str) -> tuple[Path, dict[str, Any]]:
    path = resolve_flow_script_path(reference)
    script = load_json(path)
    if not isinstance(script, dict):
        raise ValueError("flow script must be a JSON object")
    for key in ["schema_version", "script_id", "display_name", "flow"]:
        if not script.get(key):
            raise ValueError(f"flow script missing required key: {key}")
    if script["flow"] not in FLOW_CHOICES:
        raise ValueError(f"flow script has unknown flow: {script['flow']}")
    targets = script.get("targets")
    target = script.get("target")
    if not isinstance(targets, list) and not isinstance(target, dict):
        raise ValueError("flow script must contain target or targets")
    return path, script


def strip_env_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    result = []
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            result.append(char)
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == "#" and not in_single and not in_double:
            break
        result.append(char)
    return "".join(result).strip()


def parse_env_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("export "):
        text = text[7:].strip()
    if "=" not in text:
        return None
    key, raw_value = text.split("=", 1)
    key = key.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None
    value = strip_env_comment(raw_value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_env_file(env_file: Path | None, *, override: bool = False) -> list[str]:
    if env_file is None:
        return []
    path = project_path(env_file)
    if not path.exists():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def configured_env_file() -> Path:
    if LOCAL_CONFIG_PATH.exists():
        try:
            local_config = load_json(LOCAL_CONFIG_PATH)
        except (OSError, json.JSONDecodeError):
            local_config = {}
        if isinstance(local_config, dict) and isinstance(local_config.get("env_file"), str):
            return project_path(Path(local_config["env_file"]))
    return ROOT / ".env"


def model_for(provider: str, explicit_model: str | None, script: dict[str, Any] | None = None) -> str:
    if explicit_model:
        return explicit_model
    if script and isinstance(script.get("model"), str) and script["model"]:
        return script["model"]
    return DEFAULT_MODELS.get(provider, "default")


def normalized_script_config(script: dict[str, Any]) -> dict[str, Any]:
    raw_targets = script.get("targets")
    if isinstance(raw_targets, list):
        targets = raw_targets
    else:
        targets = [script["target"]]

    normalized_targets = []
    for raw_target in targets:
        if not isinstance(raw_target, dict):
            raise ValueError("each script target must be an object")
        target = json.loads(json.dumps(raw_target, ensure_ascii=False))
        if not target.get("target_id"):
            raise ValueError("script target missing target_id")
        target.setdefault("target_type", "stock")
        target.setdefault("stock_code", "")
        target.setdefault("company_name", target.get("sector_name") or target["target_id"])
        target.setdefault("market", "")
        target.setdefault("themes", [])
        target.setdefault("auto_report_enabled", True)
        normalized_targets.append(target)

    return {
        "schema_version": "flow_script_runtime_config_v1",
        "timezone": script.get("timezone", "Asia/Tokyo"),
        "targets": normalized_targets,
        "report_schedule": script.get("report_schedule", {}),
        "notebooklm": script.get("notebooklm", {}),
    }


def agent_order_from_script(script: dict[str, Any], flow: str) -> list[list[str]]:
    groups = script.get("agent_groups")
    if isinstance(groups, list) and groups:
        order: list[list[str]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            agents = group.get("agents")
            if isinstance(agents, list):
                clean_agents = [item for item in agents if isinstance(item, str) and item]
                if clean_agents:
                    order.append(clean_agents)
        if order:
            return order

    agents = script.get("agents")
    if isinstance(agents, list) and agents:
        step_agents: list[str] = []
        for item in agents:
            agent_id = item.get("agent_id") if isinstance(item, dict) else item
            if isinstance(agent_id, str) and agent_id:
                step_agents.append(agent_id)
        if step_agents:
            return [[item] for item in step_agents]

    return FLOW_AGENT_ORDER[flow]


def agent_steps_by_id(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = {}
    for item in script.get("agents", []):
        if isinstance(item, dict) and isinstance(item.get("agent_id"), str):
            steps[item["agent_id"]] = item
    return steps


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "agent"


def instruction_path_for_agent(agent_id: str) -> str | None:
    if agent_id.startswith("connector:"):
        connector = agent_id.split(":", 1)[1]
        return f"connectors/{connector}/README.md"
    return AGENT_DOC_PATHS.get(agent_id)


def command_for_cli_provider(provider: str, model: str, prompt_path: Path) -> list[str]:
    rel_prompt = rel(prompt_path)
    if provider == "codex":
        command = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--cd",
            ".",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model and model != "default":
            command.extend(["--model", model])
        command.append(f"Read {rel_prompt} and write the requested artifact files.")
        return command
    if provider == "claude":
        command = ["claude"]
        if model and model != "default":
            command.extend(["--model", model])
        command.extend(["-p", f"Read {rel_prompt} and write the requested artifact files."])
        return command
    raise ValueError(f"provider is not a CLI provider: {provider}")


def suggested_command(provider: str, model: str, prompt_path: Path) -> str:
    rel_prompt = rel(prompt_path)
    if provider in {"codex", "claude"}:
        return subprocess.list2cmdline(command_for_cli_provider(provider, model, prompt_path))
    if provider in API_ENV_KEYS:
        return f"python scripts/run_flow.py --script <script_id> --provider {provider} --model {model} --mode live"
    return f"Open {rel_prompt} and run the task manually."


def build_agent_prompt(
    *,
    agent_id: str,
    sequence: int,
    group_index: int,
    step: dict[str, Any],
    context: dict[str, Any],
    provider: str,
    model: str,
    mode: str,
) -> str:
    instruction_path = instruction_path_for_agent(agent_id)
    target = context["target"]
    script = context.get("script", {})
    required_outputs = step.get("outputs") or []
    required_inputs = step.get("inputs") or []
    notes = step.get("notes") or []
    variables = script.get("variables", {})
    rendered_outputs = [render_artifact_path(item, context) for item in required_outputs]

    return f"""# Agent Task {sequence}: {agent_id}

Provider: {provider}
Model: {model}
Mode: {mode}
Run ID: {context["run_id"]}
Flow: {context["flow"]}
Group: {group_index}

## Script

- script_id: {script.get("script_id", "-")}
- display_name: {script.get("display_name", "-")}
- depth: {script.get("depth", "-")}

## Target

```json
{json.dumps(target, indent=2, ensure_ascii=False, sort_keys=True)}
```

## Instruction Source

{instruction_path or "No local instruction file. Follow the flow script step definition."}

Read this instruction source before writing outputs.

## Context

- context_json: {context["outputs"]["context"]}
- manifest_json: {context["outputs"]["manifest"]}
- run_dir: {context["outputs"]["manifest"].rsplit("/", 1)[0]}

## Variables

```json
{json.dumps(variables, indent=2, ensure_ascii=False, sort_keys=True)}
```

## Inputs

{json.dumps(required_inputs, indent=2, ensure_ascii=False)}

## Required Outputs

{json.dumps(required_outputs, indent=2, ensure_ascii=False)}

## Write These Files

{json.dumps(rendered_outputs, indent=2, ensure_ascii=False)}

## Notes

{json.dumps(notes, indent=2, ensure_ascii=False)}

## Guardrails

- Use evidence IDs when making factual claims.
- Keep facts, interpretation, and uncertainty separate.
- Do not produce trading instructions.
- Write JSON artifacts only to the concrete paths listed in "Write These Files".
- If a requested path contains a parent directory that does not exist, create it.
- If there is not enough evidence to make an investment-related claim, write a low-confidence planning artifact instead of inventing facts.
- After the files in "Write These Files" are written, stop immediately and return a short completion message.
"""


def render_artifact_path(template: str, context: dict[str, Any]) -> str:
    run_dir = context["outputs"]["manifest"].rsplit("/", 1)[0]
    values = {
        "date": context["created_at"][:10],
        "target_id": context["target_id"],
        "run_id": context["run_id"],
        "bucket": context["bucket"],
        "run_dir": run_dir,
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def write_flow_script_runtime_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_script_artifacts(
    *,
    script: dict[str, Any],
    context: dict[str, Any],
    run_dir: Path,
    provider: str,
    model: str,
    mode: str,
) -> dict[str, str]:
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    steps = agent_steps_by_id(script)
    trace_steps = []
    sequence = 0

    for group_index, group in enumerate(context["agent_order"], start=1):
        for agent_id in group:
            sequence += 1
            step = steps.get(agent_id, {})
            prompt_path = prompts_dir / f"{sequence:02d}_{safe_filename(agent_id)}.md"
            prompt = build_agent_prompt(
                agent_id=agent_id,
                sequence=sequence,
                group_index=group_index,
                step=step,
                context=context,
                provider=provider,
                model=model,
                mode=mode,
            )
            prompt_path.write_text(prompt, encoding="utf-8")
            trace_steps.append(
                {
                    "sequence": sequence,
                    "group": group_index,
                    "agent_id": agent_id,
                    "instruction_path": instruction_path_for_agent(agent_id),
                    "model": model,
                    "prompt_path": rel(prompt_path),
                    "expected_outputs": [render_artifact_path(item, context) for item in (step.get("outputs") or [])],
                    "suggested_command": suggested_command(provider, model, prompt_path),
                    "status": "planned",
                }
            )

    trace_path = run_dir / "agent_trace.json"
    trace = {
        "schema_version": "agent_trace_v1",
        "created_at": now_jst(),
        "script_id": script["script_id"],
        "run_id": context["run_id"],
        "provider": provider,
        "model": model,
        "mode": mode,
        "steps": trace_steps,
    }
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    paths = {
        "agent_trace": rel(trace_path),
        "prompts_dir": rel(prompts_dir),
    }
    if mode == "simulate":
        paths.update(write_simulated_outputs(context=context, run_dir=run_dir))
    return paths


def rendered_script_outputs(script: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for step in script.get("agents", []):
        if not isinstance(step, dict):
            continue
        agent_id = step.get("agent_id")
        for index, template in enumerate(step.get("outputs", []), start=1):
            if not isinstance(template, str):
                continue
            key_base = output_key_for_template(template, agent_id, index)
            key = key_base
            suffix = 2
            while key in outputs:
                key = f"{key_base}_{suffix}"
                suffix += 1
            outputs[key] = render_artifact_path(template, context)
    return outputs


def output_key_for_template(template: str, agent_id: Any, index: int) -> str:
    filename = Path(template).name
    canonical = {
        "evidence.json": "evidence",
        "agent_outputs.json": "agent_outputs",
        "report_judge.json": "report_judge",
        "chat_judge.json": "chat_judge",
        "health.json": "health",
    }
    if filename in canonical:
        return canonical[filename]
    return safe_filename(f"{agent_id or 'agent'}_{filename or index}")


def script_context_outputs(script: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    outputs = {
        "manifest": context["outputs"]["manifest"],
        "context": context["outputs"]["context"],
    }
    outputs.update(rendered_script_outputs(script, context))
    return outputs


def existing_script_output_paths(outputs: dict[str, str]) -> dict[str, str]:
    existing = {}
    for key, path_text in outputs.items():
        path = project_path(Path(path_text))
        if path.is_file() and path.stat().st_size > 0:
            existing[f"script_output_{key}"] = path_text
    return existing


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def expected_outputs_exist(step: dict[str, Any]) -> bool:
    outputs = step.get("expected_outputs")
    if not isinstance(outputs, list) or not outputs:
        return False
    for item in outputs:
        if not isinstance(item, str):
            return False
        path = project_path(Path(item))
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
    return True


def api_request_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def call_api_provider(provider: str, model: str, prompt: str) -> dict[str, Any]:
    env_key = API_ENV_KEYS[provider]
    api_key = os.environ.get(env_key)
    if not api_key:
        raise RuntimeError(f"{env_key} is not set")

    if provider == "openai_api":
        return api_request_json(
            "https://api.openai.com/v1/responses",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": prompt,
            },
        )

    if provider == "anthropic_api":
        return api_request_json(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if provider == "gemini_api":
        model_path = urllib.parse.quote(model, safe="")
        return api_request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent?key={api_key}",
            {"Content-Type": "application/json"},
            {"contents": [{"parts": [{"text": prompt}]}]},
        )

    raise ValueError(f"provider is not an API provider: {provider}")


def execute_trace_steps(
    *,
    trace_path: Path,
    provider: str,
    model: str,
    run_dir: Path,
    step_timeout: int | None,
) -> tuple[int, dict[str, str]]:
    trace = load_json(trace_path)
    if not isinstance(trace, dict) or not isinstance(trace.get("steps"), list):
        raise ValueError("agent_trace.json is invalid")

    responses_dir = run_dir / "llm_responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    returncode = 0

    for step in trace["steps"]:
        if not isinstance(step, dict):
            continue
        prompt_rel = step.get("prompt_path")
        if not isinstance(prompt_rel, str):
            continue
        prompt_path = project_path(Path(prompt_rel))
        response_path = responses_dir / f"{int(step['sequence']):02d}_{safe_filename(step['agent_id'])}.json"
        step["status"] = "running"
        write_json(trace_path, trace)

        try:
            if provider in {"codex", "claude"}:
                command = command_for_cli_provider(provider, model, prompt_path)
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=step_timeout,
                )
                payload = {
                    "schema_version": "llm_response_v1",
                    "provider": provider,
                    "model": model,
                    "agent_id": step.get("agent_id"),
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
                if result.returncode != 0:
                    returncode = result.returncode
                    step["status"] = "failed"
                else:
                    step["status"] = "completed"
            elif provider in API_ENV_KEYS:
                payload = {
                    "schema_version": "llm_response_v1",
                    "provider": provider,
                    "model": model,
                    "agent_id": step.get("agent_id"),
                    "response": call_api_provider(provider, model, read_prompt(prompt_path)),
                }
                step["status"] = "completed"
            else:
                payload = {
                    "schema_version": "llm_response_v1",
                    "provider": provider,
                    "model": model,
                    "agent_id": step.get("agent_id"),
                    "message": "Manual provider does not execute automatically.",
                }
                step["status"] = "skipped"
        except Exception as exc:  # pragma: no cover - exercised by integration use.
            payload = {
                "schema_version": "llm_response_v1",
                "provider": provider,
                "model": model,
                "agent_id": step.get("agent_id"),
                "error": str(exc),
            }
            if isinstance(exc, subprocess.TimeoutExpired):
                payload["command"] = exc.cmd
                payload["stdout"] = text_or_empty(exc.output)
                payload["stderr"] = text_or_empty(exc.stderr)
                payload["timeout_seconds"] = step_timeout
                if expected_outputs_exist(step):
                    payload["warning"] = "process_timed_out_after_expected_outputs_were_written"
                    step["status"] = "completed_with_timeout"
                else:
                    step["status"] = "failed"
                    returncode = 1
            else:
                step["status"] = "failed"
                returncode = 1

        write_json(response_path, payload)
        step["response_path"] = rel(response_path)
        trace["updated_at"] = now_jst()
        write_json(trace_path, trace)
        if returncode != 0:
            break

    return returncode, {"llm_responses": rel(responses_dir)}


def trace_has_timeout_completion(trace_path: Path) -> bool:
    trace = load_json(trace_path)
    if not isinstance(trace, dict) or not isinstance(trace.get("steps"), list):
        return False
    return any(step.get("status") == "completed_with_timeout" for step in trace["steps"] if isinstance(step, dict))


def report_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": target.get("target_id", ""),
        "target_type": target.get("target_type", "stock"),
        "stock_code": target.get("stock_code", ""),
        "company_name": target.get("company_name") or target.get("sector_name") or target.get("target_id", ""),
        "market": target.get("market", ""),
        "themes": target.get("themes", []),
    }


def write_simulated_outputs(*, context: dict[str, Any], run_dir: Path) -> dict[str, str]:
    now = now_jst()
    target = context["target"]
    paths: dict[str, str] = {}

    if "evidence" in context["outputs"]:
        evidence_path = run_dir / "evidence.json"
        evidence_path.write_text("[]\n", encoding="utf-8")
        paths["evidence"] = rel(evidence_path)

    analysis_agents = [
        agent_id
        for group in context["agent_order"]
        for agent_id in group
        if agent_id in ANALYSIS_AGENTS
    ]
    if analysis_agents:
        agent_outputs_path = run_dir / "agent_outputs.json"
        agent_outputs = {
            "schema_version": "agent_outputs_bundle_v1",
            "target_id": context["target_id"],
            "report_date": context["created_at"][:10],
            "agent_outputs": [
                {
                    "schema_version": "agent_output_v1",
                    "agent_name": agent_id,
                    "run_id": context["run_id"],
                    "stance": f"{agent_id} placeholder stance",
                    "conclusion": "Simulation only. Replace this file with real Agent output after running the prompt.",
                    "claim_strength": 0,
                    "confidence": "low",
                    "evidence_ids": [],
                    "key_points": [
                        "Prompt generation and artifact routing were verified.",
                        "No market data was fetched in simulation mode."
                    ],
                    "limitations": [
                        "This is not an investment readout.",
                        "Run the planned Agent prompts to produce evidence-backed analysis."
                    ],
                }
                for agent_id in analysis_agents
            ],
        }
        agent_outputs_path.write_text(json.dumps(agent_outputs, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        paths["agent_outputs"] = rel(agent_outputs_path)

    if "report_judge" in context["outputs"]:
        report_path = run_dir / "report_judge.json"
        report = {
            "schema_version": "report_readout_v1",
            "run_id": context["run_id"],
            "agent_name": "report_judge",
            "run_at": now,
            "decision_stage": "draft",
            "target": report_target(target),
            "market_readout": {
                "label": "pending",
                "evidence_balance_score": 0,
                "confidence": "low",
                "summary": "Simulation only. Real evidence and Agent outputs have not been produced yet.",
            },
            "information_status": {
                "label": "insufficient_information",
                "summary": "The flow routing was tested without external data collection.",
            },
            "hypothesis_impact": {
                "label": "undetermined",
                "summary": "No evidence-backed hypothesis update was made in simulation mode.",
            },
            "uncertainty": {
                "level": "high",
                "factors": ["No connector output", "No evidence IDs", "No real Agent execution"],
            },
            "evidence_weight": {
                "upside": 0,
                "downside": 0,
                "contradiction": 0,
                "priced_in": 100,
            },
            "view_change_conditions": [],
            "missing_information": [
                {
                    "item": "Latest semiconductor sector evidence",
                    "importance": "high",
                    "reason": "Simulation mode does not fetch or evaluate live information.",
                }
            ],
            "used_evidence": [],
            "warnings": ["simulation_only"],
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        paths["report_judge"] = rel(report_path)

    if "health" in context["outputs"]:
        health_path = run_dir / "health.json"
        health = {
            "schema_version": "health_snapshot_v1",
            "run_id": context["run_id"],
            "run_at": now,
            "target_id": context["target_id"],
            "overall_status": "info",
            "summary": "Simulation completed. Agent prompts and routing artifacts were generated.",
            "stats": {
                "planned_steps": sum(len(group) for group in context["agent_order"]),
                "simulated_agent_outputs": len(analysis_agents),
            },
            "sections": [
                {
                    "section_id": "simulation",
                    "title": "Simulation",
                    "checks": [
                        {
                            "check_id": "prompt_generation",
                            "label": "Prompt generation",
                            "status": "ok",
                            "message": "Prompt files were generated for each planned Agent step.",
                            "detail": "No external connector or LLM command was executed.",
                            "last_run_at": now,
                        }
                    ],
                }
            ],
        }
        health_path.write_text(json.dumps(health, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        paths["health"] = rel(health_path)

    return paths


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
    provider: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    script: dict[str, Any] | None = None,
    env_file: Path | None = None,
    loaded_env_keys: list[str] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
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
    if provider:
        manifest["provider"] = provider
    if model:
        manifest["model"] = model
    if mode:
        manifest["mode"] = mode
    if script:
        manifest["script"] = {
            "script_id": script["script_id"],
            "display_name": script.get("display_name"),
            "description": script.get("description"),
        }
    if env_file:
        manifest["secrets"] = {
            "env_file": rel(env_file),
            "loaded_env_keys": sorted(loaded_env_keys or []),
            "values_exposed": False,
        }
    return manifest


def run_agent_command(command: list[str], context_path: Path, run_dir: Path) -> int:
    env = os.environ.copy()
    env["AGENT_CONTEXT_JSON"] = str(context_path)
    env["AGENT_RUN_DIR"] = str(run_dir)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, check=False)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and optionally run an Agent Team flow.")
    parser.add_argument("--flow", choices=FLOW_CHOICES)
    parser.add_argument("--script", help="Flow script id or JSON path under system/config/flow_scripts.")
    parser.add_argument("--provider", choices=PROVIDER_CHOICES)
    parser.add_argument("--model", help="Model name for CLI/API providers. Use 'default' to let the provider choose.")
    parser.add_argument("--mode", choices=MODE_CHOICES)
    parser.add_argument("--target-id")
    parser.add_argument("--date", default=today_jst())
    parser.add_argument("--run-id")
    parser.add_argument("--config", type=Path, default=ROOT / "system/config/app.example.json")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Load API keys and local secrets from this file. Defaults to system/config/local.json env_file or .env.",
    )
    parser.add_argument("--no-env-file", action="store_true", help="Do not load local secrets from an env file.")
    parser.add_argument(
        "--step-timeout",
        type=int,
        default=300,
        help="Maximum seconds to allow each live Agent step to run. Use 0 to disable.",
    )
    parser.add_argument(
        "--agent-command",
        nargs=argparse.REMAINDER,
        help="Optional command to run after context creation. Everything after this flag is executed.",
    )
    args = parser.parse_args()

    env_file = None if args.no_env_file else project_path(args.env_file) if args.env_file else configured_env_file()
    loaded_env_keys = load_env_file(env_file)

    script_path: Path | None = None
    script: dict[str, Any] | None = None
    script_runtime_config: dict[str, Any] | None = None
    if args.script:
        script_path, script = load_flow_script(args.script)
        script_runtime_config = normalized_script_config(script)

    flow = args.flow or (script["flow"] if script else None)
    if flow is None:
        parser.error("--flow is required unless --script is provided")

    provider = args.provider or (script.get("provider") if script else None) or "manual"
    model = model_for(provider, args.model, script)
    mode = args.mode or (script.get("mode") if script else None) or "prepare"

    config_path = project_path(args.config)
    runs_dir = project_path(args.runs_dir)
    if script_runtime_config is not None:
        target_id = args.target_id or script_runtime_config["targets"][0]["target_id"]
    else:
        target_id = select_target_id(config_path, args.target_id)

    run_id = args.run_id or default_run_id(flow, args.date, target_id)
    bucket = FLOW_TO_BUCKET[flow]
    run_dir = runs_dir / args.date / target_id / bucket
    context_path = run_dir / "context.json"
    manifest_path = run_dir / "manifest.json"

    run_dir.mkdir(parents=True, exist_ok=True)
    if script_runtime_config is not None:
        config_path = run_dir / "script_config.json"
        write_flow_script_runtime_config(config_path, script_runtime_config)

    context = build_context(
        flow=flow,
        target_id=target_id,
        run_id=run_id,
        run_dir=run_dir,
        config_path=config_path,
    )
    if script:
        context["script"] = {
            "script_id": script["script_id"],
            "display_name": script.get("display_name"),
            "description": script.get("description"),
            "script_path": rel(script_path) if script_path else None,
            "depth": script.get("depth", "normal"),
            "provider": provider,
            "model": model,
            "mode": mode,
            "variables": script.get("variables", {}),
            "outputs": script.get("outputs", []),
            "automation": script.get("automation", {}),
        }
        context["agent_order"] = agent_order_from_script(script, flow)
        context["outputs"] = script_context_outputs(script, context)

    write_context(context, context_path)

    agent_command = args.agent_command or None
    manifest = build_manifest(
        run_id=run_id,
        flow=flow,
        date=args.date,
        target_id=target_id,
        run_dir=run_dir,
        context_path=context_path,
        root=ROOT,
        status="prepared",
        agent_command=agent_command,
        provider=provider,
        model=model,
        mode=mode,
        script=script,
        env_file=env_file,
        loaded_env_keys=loaded_env_keys,
    )
    if script:
        script_paths = write_script_artifacts(
            script=script,
            context=context,
            run_dir=run_dir,
            provider=provider,
            model=model,
            mode=mode,
        )
        manifest["paths"].update(script_paths)
        script_outputs = rendered_script_outputs(script, context)
        if script_outputs:
            manifest["expected_script_outputs"] = script_outputs

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

    if script and mode == "live" and not agent_command:
        trace_path = run_dir / "agent_trace.json"
        manifest["status"] = "running"
        manifest["updated_at"] = now_jst()
        write_manifest(manifest_path, manifest)
        try:
            returncode, live_paths = execute_trace_steps(
                trace_path=trace_path,
                provider=provider,
                model=model,
                run_dir=run_dir,
                step_timeout=None if args.step_timeout == 0 else args.step_timeout,
            )
            manifest["paths"].update(live_paths)
            if script:
                manifest["paths"].update(existing_script_output_paths(rendered_script_outputs(script, context)))
            if returncode == 0 and trace_has_timeout_completion(trace_path):
                manifest["status"] = "completed_with_warnings"
            else:
                manifest["status"] = "completed" if returncode == 0 else "failed"
            manifest["returncode"] = returncode
        except KeyboardInterrupt:
            returncode = 130
            manifest["status"] = "failed"
            manifest["returncode"] = returncode
        finally:
            manifest["updated_at"] = now_jst()
            write_manifest(manifest_path, manifest)

    print(f"manifest: {manifest_path}")
    print(f"context: {context_path}")
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
