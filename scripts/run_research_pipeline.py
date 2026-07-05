#!/usr/bin/env python3
"""Run a production-shaped research pipeline into runs/YYYY-MM-DD/target/bucket."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator as JsonSchemaValidator
except ImportError:
    from jsonschema import Draft7Validator as JsonSchemaValidator


ROOT = Path(__file__).resolve().parents[1]
JQUANTS_DIR = ROOT / "connectors" / "jquants"
if str(JQUANTS_DIR) not in sys.path:
    sys.path.insert(0, str(JQUANTS_DIR))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from build_evidence import evidence_from_normalized  # noqa: E402
from build_history import build_history  # noqa: E402
from build_indicators import evidence_from_indicators, indicators_from_normalized  # noqa: E402
from build_relative_comparison import evidence_from_relative_comparison, relative_comparison_from_normalized, safe_slug as safe_comparison_slug  # noqa: E402
from fetch_daily_quotes import fetch_and_save  # noqa: E402
from generate_reports import build_analysis_markdown, build_audio_markdown, build_html_report  # noqa: E402
from normalize_daily_quotes import normalize_raw  # noqa: E402
from run_agent_team_llm import assert_no_secret_leak, load_json as load_any_json, secret_values, validate_payload  # noqa: E402
from run_flow import configured_env_file, load_env_file  # noqa: E402


JST = timezone(timedelta(hours=9))
CONTRACTS = ROOT / "system" / "contracts"


@dataclass(frozen=True)
class PipelineConfig:
    target_id: str
    code: str
    stock_code: str
    company_name: str
    date: str
    bucket: str = "morning"
    market: str = ""
    themes: tuple[str, ...] = ()
    provider: str = "codex_cli"
    model: str = "gpt-5.4-mini"
    codex_reasoning_effort: str = "low"
    codex_timeout: int = 600
    agent_timeout: int = 0
    max_attempts: int = 2
    out_root: Path = ROOT / "runs"
    raw: Path | None = None
    history_raws: tuple[Path, ...] = ()
    env_file: Path | None = None
    timeout: int = 60
    save_prompt: bool = False
    save_raw_response: bool = False
    resume_agent_sequence: bool = False
    publish_reports: bool = True
    include_edinet: bool = False
    edinet_raw: Path | None = None
    edinet_doc_type: str = "2"
    agent_execution: str = "combined"
    include_derived_indicators: bool = True
    include_news: bool = False
    news_raw: Path | None = None
    news_query: str = ""
    news_language: str = "en"
    news_rss_url: str = ""
    include_ir: bool = False
    ir_raw: Path | None = None
    ir_url: str = ""
    comparison_raws: tuple[str, ...] = ()
    comparison_codes: tuple[str, ...] = ()


def now_jst() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EDINET_FETCH = load_module("pipeline_edinet_fetch_documents", ROOT / "connectors" / "edinet" / "fetch_documents.py")
EDINET_BUILD = load_module("pipeline_edinet_build_evidence", ROOT / "connectors" / "edinet" / "build_evidence.py")
NEWS_FETCH = load_module("pipeline_news_fetch_articles", ROOT / "connectors" / "news" / "fetch_articles.py")
NEWS_RSS_FETCH = load_module("pipeline_news_fetch_rss", ROOT / "connectors" / "news" / "fetch_rss.py")
NEWS_BUILD = load_module("pipeline_news_build_evidence", ROOT / "connectors" / "news" / "build_evidence.py")
IR_FETCH = load_module("pipeline_ir_fetch_page", ROOT / "connectors" / "ir" / "fetch_page.py")
IR_BUILD = load_module("pipeline_ir_build_evidence", ROOT / "connectors" / "ir" / "build_evidence.py")


def run_dir(config: PipelineConfig) -> Path:
    return config.out_root / config.date / config.target_id / config.bucket


def check(check_id: str, label: str, status: str, message: str, detail: str = "") -> dict[str, Any]:
    return {
        "check_id": check_id,
        "label": label,
        "status": status,
        "message": message,
        "detail": detail,
        "last_run_at": now_jst(),
    }


def health_payload(
    *,
    config: PipelineConfig,
    run_id: str,
    status: str,
    summary: str,
    checks: list[dict[str, Any]],
    evidence_count: int = 0,
    agent_success: int = 0,
    agent_failed: int = 0,
    report_outputs: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "health_snapshot_v1",
        "run_id": run_id,
        "run_at": now_jst(),
        "target_id": config.target_id,
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
                "section_id": "pipeline",
                "title": "Research Pipeline",
                "checks": checks,
            }
        ],
    }


def validate_contract(schema_name: str, instance: Any) -> None:
    schema = load_json(CONTRACTS / schema_name)
    JsonSchemaValidator(schema).validate(instance)


def normalize_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def copy_raw_to_run(raw_path: Path, destination_root: Path) -> Path:
    raw = load_json(raw_path)
    date = str(raw.get("date") or "unknown")
    target_id = str(raw.get("target_id") or "unknown")
    code = str(raw.get("code") or "unknown")
    destination = destination_root / normalize_date(date) / target_id / f"daily_quotes_{code}_{date.replace('-', '')}_raw.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, destination)
    return destination


def copy_history_raws_to_run(raw_paths: tuple[Path, ...], destination_root: Path) -> list[Path]:
    return [copy_raw_to_run(path, destination_root) for path in raw_paths]


def copy_edinet_raw_to_run(raw_path: Path, destination_root: Path) -> Path:
    raw = load_json(raw_path)
    date = str(raw.get("date") or "unknown")
    target_id = str(raw.get("target_id") or "unknown")
    destination = destination_root / normalize_date(date) / target_id / f"documents_{normalize_date(date)}_raw.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, destination)
    return destination


def copy_news_raw_to_run(raw_path: Path, destination_root: Path) -> Path:
    raw = load_json(raw_path)
    date = str(raw.get("date") or "unknown")
    target_id = str(raw.get("target_id") or "unknown")
    destination = destination_root / normalize_date(date) / target_id / f"articles_{normalize_date(date)}_raw.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, destination)
    return destination


def copy_ir_raw_to_run(raw_path: Path, destination_root: Path, date: str) -> Path:
    raw = load_json(raw_path)
    target_id = str(raw.get("target_id") or "unknown")
    url = str(raw.get("url") or "ir_page")
    destination = destination_root / normalize_date(date) / target_id / f"{IR_FETCH.safe_slug(url)}_raw.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, destination)
    return destination


def parse_labeled_value(value: str, *, expected: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"{expected} must be LABEL=VALUE")
    label, item = value.split("=", 1)
    if not label.strip() or not item.strip():
        raise ValueError(f"{expected} must be LABEL=VALUE")
    return label.strip(), item.strip()


def copy_comparison_raw_to_run(raw_path: Path, destination_root: Path, label: str, date: str, target_id: str) -> Path:
    raw = load_json(raw_path)
    code = str(raw.get("code") or safe_comparison_slug(label))
    destination = destination_root / normalize_date(date) / target_id / f"{safe_comparison_slug(label)}_{code}_{date.replace('-', '')}_raw.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, destination)
    return destination


def write_reports(evidence: list[dict[str, Any]], agents: dict[str, Any], judge: dict[str, Any], out_dir: Path) -> list[Path]:
    target = judge["target"]
    report_date = agents["report_date"]
    prefix = f"{report_date}_{target['stock_code']}_close"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        f"{prefix}_analysis.md": build_analysis_markdown(evidence, agents, judge),
        f"{prefix}_audio.md": build_audio_markdown(evidence, agents, judge),
        f"{prefix}.html": build_html_report(evidence, agents, judge),
    }
    paths = []
    for filename, content in outputs.items():
        path = out_dir / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def run_llm_step(config: PipelineConfig, evidence_path: Path, output_dir: Path, run_id: str) -> None:
    script_name = "run_agent_sequence.py" if config.agent_execution == "sequential" else "run_agent_team_llm.py"
    command = [
        sys.executable,
        str(ROOT / "scripts" / script_name),
        "--evidence",
        str(evidence_path),
        "--out-dir",
        str(output_dir),
        "--target-id",
        config.target_id,
        "--stock-code",
        config.stock_code,
        "--company-name",
        config.company_name,
        "--market",
        config.market,
        "--report-date",
        config.date,
        "--run-id",
        run_id,
        "--provider",
        config.provider,
        "--model",
        config.model,
        "--codex-reasoning-effort",
        config.codex_reasoning_effort,
        "--codex-timeout",
        str(config.codex_timeout),
        "--max-attempts",
        str(config.max_attempts),
    ]
    for theme in config.themes:
        command.extend(["--theme", theme])
    if config.env_file:
        command.extend(["--env-file", str(config.env_file)])
    if config.save_prompt and config.agent_execution == "combined":
        command.append("--save-prompt")
    if config.save_raw_response:
        command.append("--save-raw-responses" if config.agent_execution == "sequential" else "--save-raw-response")
    if config.save_prompt and config.agent_execution == "sequential":
        command.append("--save-prompts")
    if config.resume_agent_sequence and config.agent_execution == "sequential":
        command.append("--resume")

    subprocess_timeout = config.agent_timeout
    if subprocess_timeout <= 0:
        step_count = 7 if config.agent_execution == "sequential" else 1
        subprocess_timeout = config.codex_timeout * step_count + 120
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=subprocess_timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(
            "AgentTeam LLM step timed out\n"
            f"timeout_seconds={subprocess_timeout}\n"
            f"command={' '.join(command)}\n"
            f"stdout={stdout[:4000]}\n"
            f"stderr={stderr[:4000]}"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            "AgentTeam LLM step failed\n"
            f"command={' '.join(command)}\n"
            f"stdout={completed.stdout[:4000]}\n"
            f"stderr={completed.stderr[:4000]}"
        )


def collect_agent_sequence_paths(directory: Path, paths: dict[str, str]) -> None:
    sequence_manifest_path = directory / "agent_sequence_manifest.json"
    sequence_health_path = directory / "agent_sequence_health.json"
    sequence_status_path = directory / "agent_sequence_status.json"
    if sequence_manifest_path.is_file():
        paths["agent_sequence_manifest"] = str(sequence_manifest_path)
    if sequence_health_path.is_file():
        paths["agent_sequence_health"] = str(sequence_health_path)
    if sequence_status_path.is_file():
        paths["agent_sequence_status"] = str(sequence_status_path)
    agent_steps_dir = directory / "agent_steps"
    if agent_steps_dir.exists():
        paths["agent_steps_dir"] = str(agent_steps_dir)


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    date = normalize_date(config.date)
    config = PipelineConfig(**{**config.__dict__, "date": date})
    run_id = f"PIPE-{date.replace('-', '')}-{config.target_id}-{config.bucket.upper()}"
    directory = run_dir(config)
    directory.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    paths: dict[str, str] = {}
    evidence_count_so_far = 0
    loaded_keys = load_env_file(config.env_file or configured_env_file())
    secrets = secret_values(loaded_keys + ["JQUANTS_API_KEY", "EDINET_API_KEY", "NEWS_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"])

    manifest_path = directory / "pipeline_manifest.json"
    health_path = directory / "health.json"
    try:
        raw_root = directory / "raw" / "jquants"
        if config.raw:
            raw_path = copy_raw_to_run(config.raw, raw_root)
            checks.append(check("jquants_raw", "J-Quants raw", "ok", "Raw artifact copied into run directory.", str(raw_path)))
        else:
            api_key = os.environ.get("JQUANTS_API_KEY", "")
            if not api_key:
                raise RuntimeError("JQUANTS_API_KEY is not set")
            raw_path = fetch_and_save(
                api_key=api_key,
                target_id=config.target_id,
                code=config.code,
                date=date,
                out_root=raw_root,
                timeout=config.timeout,
            )
            checks.append(check("jquants_raw", "J-Quants raw", "ok", "Raw artifact fetched into run directory.", str(raw_path)))
        paths["raw"] = str(raw_path)

        raw = load_json(raw_path)
        if config.history_raws:
            history_raw_paths = copy_history_raws_to_run(config.history_raws, raw_root)
            history_inputs = sorted({raw_path, *history_raw_paths})
            normalized = build_history(history_inputs)
            checks.append(check("jquants_history", "J-Quants history", "ok", f"{normalized.get('record_count', 0)} historical record(s) combined.", f"{len(history_inputs)} raw file(s)"))
        else:
            normalized = normalize_raw(raw, raw_path=raw_path)
        normalized_path = directory / "normalized" / "jquants" / date / f"{config.target_id}.json"
        write_json(normalized_path, normalized)
        checks.append(check("jquants_normalized", "J-Quants normalized", "ok", f"{normalized.get('record_count', 0)} record(s) normalized.", str(normalized_path)))
        paths["normalized"] = str(normalized_path)

        evidence = evidence_from_normalized(normalized, stock_code=config.stock_code, company_name=config.company_name)
        if config.include_derived_indicators:
            indicators = indicators_from_normalized(normalized)
            indicators_path = directory / "derived" / "jquants" / "indicators.json"
            write_json(indicators_path, indicators)
            indicator_evidence = evidence_from_indicators(
                indicators,
                stock_code=config.stock_code,
                company_name=config.company_name,
            )
            evidence.extend(indicator_evidence)
            status = "ok" if indicator_evidence else "warn"
            checks.append(check("jquants_indicators", "J-Quants derived indicators", status, f"{len(indicator_evidence)} derived indicator Evidence item(s) added.", str(indicators_path)))
            paths["jquants_indicators"] = str(indicators_path)
        if config.comparison_raws or config.comparison_codes:
            comparison_raw_root = directory / "raw" / "jquants_comparison"
            comparison_normalized_root = directory / "normalized" / "jquants_comparison" / date
            benchmarks: list[dict[str, Any]] = []
            for raw_spec in config.comparison_raws:
                label, raw_value = parse_labeled_value(raw_spec, expected="--comparison-raw")
                source_path = Path(raw_value)
                source_path = source_path if source_path.is_absolute() else ROOT / source_path
                comparison_raw_path = copy_comparison_raw_to_run(source_path, comparison_raw_root, label, date, config.target_id)
                comparison_raw = load_json(comparison_raw_path)
                comparison_normalized = normalize_raw(comparison_raw, raw_path=comparison_raw_path)
                comparison_normalized_path = comparison_normalized_root / f"{safe_comparison_slug(label)}.json"
                write_json(comparison_normalized_path, comparison_normalized)
                benchmarks.append({"label": label, "normalized": comparison_normalized})
                paths[f"comparison_raw_{safe_comparison_slug(label)}"] = str(comparison_raw_path)
                paths[f"comparison_normalized_{safe_comparison_slug(label)}"] = str(comparison_normalized_path)
            for code_spec in config.comparison_codes:
                label, code_value = parse_labeled_value(code_spec, expected="--comparison-code")
                api_key = os.environ.get("JQUANTS_API_KEY", "")
                if not api_key:
                    raise RuntimeError("JQUANTS_API_KEY is not set")
                comparison_raw_path = fetch_and_save(
                    api_key=api_key,
                    target_id=f"{config.target_id}-{safe_comparison_slug(label)}",
                    code=code_value,
                    date=date,
                    out_root=comparison_raw_root,
                    timeout=config.timeout,
                )
                comparison_raw = load_json(comparison_raw_path)
                comparison_normalized = normalize_raw(comparison_raw, raw_path=comparison_raw_path)
                comparison_normalized_path = comparison_normalized_root / f"{safe_comparison_slug(label)}.json"
                write_json(comparison_normalized_path, comparison_normalized)
                benchmarks.append({"label": label, "normalized": comparison_normalized})
                paths[f"comparison_raw_{safe_comparison_slug(label)}"] = str(comparison_raw_path)
                paths[f"comparison_normalized_{safe_comparison_slug(label)}"] = str(comparison_normalized_path)
            relative_comparison = relative_comparison_from_normalized(
                target_normalized=normalized,
                benchmarks=benchmarks,
            )
            relative_comparison_path = directory / "derived" / "jquants" / "relative_comparison.json"
            write_json(relative_comparison_path, relative_comparison)
            comparison_evidence = evidence_from_relative_comparison(
                relative_comparison,
                stock_code=config.stock_code,
                company_name=config.company_name,
            )
            evidence.extend(comparison_evidence)
            status = "ok" if comparison_evidence else "warn"
            checks.append(check("jquants_relative_comparison", "J-Quants relative comparison", status, f"{len(comparison_evidence)} relative comparison Evidence item(s) added.", str(relative_comparison_path)))
            paths["jquants_relative_comparison"] = str(relative_comparison_path)
        if config.include_edinet or config.edinet_raw:
            edinet_root = directory / "raw" / "edinet"
            if config.edinet_raw:
                edinet_raw_path = copy_edinet_raw_to_run(config.edinet_raw, edinet_root)
                checks.append(check("edinet_raw", "EDINET raw", "ok", "EDINET raw artifact copied into run directory.", str(edinet_raw_path)))
            else:
                edinet_key = os.environ.get("EDINET_API_KEY", "")
                if not edinet_key:
                    raise RuntimeError("EDINET_API_KEY is not set")
                edinet_raw_path = EDINET_FETCH.fetch_and_save(
                    api_key=edinet_key,
                    target_id=config.target_id,
                    date=date,
                    out_root=edinet_root,
                    doc_type=config.edinet_doc_type,
                    timeout=config.timeout,
                )
                checks.append(check("edinet_raw", "EDINET raw", "ok", "EDINET raw artifact fetched into run directory.", str(edinet_raw_path)))
            paths["edinet_raw"] = str(edinet_raw_path)
            edinet_raw = load_json(edinet_raw_path)
            edinet_evidence = EDINET_BUILD.evidence_from_raw(
                edinet_raw,
                stock_code=config.stock_code,
                company_name=config.company_name,
                sec_code=config.stock_code,
                filer_name_contains=config.company_name,
            )
            evidence.extend(edinet_evidence)
            status = "ok" if edinet_evidence else "warn"
            checks.append(check("edinet_evidence", "EDINET Evidence", status, f"{len(edinet_evidence)} EDINET Evidence item(s) added.", str(edinet_raw_path)))
        if config.include_news or config.news_raw:
            news_root = directory / "raw" / "news"
            if config.news_raw:
                news_raw_path = copy_news_raw_to_run(config.news_raw, news_root)
                checks.append(check("news_raw", "News raw", "ok", "News raw artifact copied into run directory.", str(news_raw_path)))
            else:
                news_key = os.environ.get("NEWS_API_KEY", "")
                query = config.news_query or f'"{config.company_name}" OR {config.stock_code}'
                if news_key:
                    news_raw_path = NEWS_FETCH.fetch_and_save(
                        api_key=news_key,
                        target_id=config.target_id,
                        query=query,
                        date=date,
                        out_root=news_root,
                        language=config.news_language,
                        sort_by="publishedAt",
                        page_size=20,
                        timeout=config.timeout,
                    )
                    checks.append(check("news_raw", "News raw", "ok", "NewsAPI raw artifact fetched into run directory.", str(news_raw_path)))
                else:
                    news_raw_path = NEWS_RSS_FETCH.fetch_and_save(
                        target_id=config.target_id,
                        query=query,
                        date=date,
                        out_root=news_root,
                        language=config.news_language,
                        timeout=config.timeout,
                        max_items=10,
                        rss_url=config.news_rss_url,
                    )
                    checks.append(check("news_raw", "News raw", "ok", "RSS news raw artifact fetched into run directory.", str(news_raw_path)))
            paths["news_raw"] = str(news_raw_path)
            news_raw = load_json(news_raw_path)
            news_evidence = NEWS_BUILD.evidence_from_raw(
                news_raw,
                stock_code=config.stock_code,
                company_name=config.company_name,
            )
            evidence.extend(news_evidence)
            status = "ok" if news_evidence else "warn"
            checks.append(check("news_evidence", "News Evidence", status, f"{len(news_evidence)} News Evidence item(s) added.", str(news_raw_path)))
        if config.include_ir or config.ir_raw:
            ir_root = directory / "raw" / "ir"
            if config.ir_raw:
                ir_raw_path = copy_ir_raw_to_run(config.ir_raw, ir_root, date)
                checks.append(check("ir_raw", "Official IR raw", "ok", "Official IR raw artifact copied into run directory.", str(ir_raw_path)))
            else:
                if not config.ir_url:
                    raise RuntimeError("--ir-url is required when --include-ir is used without --ir-raw")
                ir_raw_path = IR_FETCH.fetch_and_save(
                    target_id=config.target_id,
                    company_name=config.company_name,
                    url=config.ir_url,
                    date=date,
                    out_root=ir_root,
                    timeout=config.timeout,
                )
                checks.append(check("ir_raw", "Official IR raw", "ok", "Official IR raw artifact fetched into run directory.", str(ir_raw_path)))
            paths["ir_raw"] = str(ir_raw_path)
            ir_raw = load_json(ir_raw_path)
            ir_evidence = IR_BUILD.evidence_from_raw(
                ir_raw,
                stock_code=config.stock_code,
                company_name=config.company_name,
                date=date,
            )
            evidence.extend(ir_evidence)
            status = "ok" if ir_evidence else "warn"
            checks.append(check("ir_evidence", "Official IR Evidence", status, f"{len(ir_evidence)} Official IR Evidence item(s) added.", str(ir_raw_path)))
        evidence_path = directory / "evidence.json"
        write_json(evidence_path, evidence)
        validate_contract("evidence.schema.json", evidence)
        evidence_count_so_far = len(evidence)
        checks.append(check("evidence_contract", "Evidence contract", "ok", f"{len(evidence)} Evidence item(s) validated.", str(evidence_path)))
        paths["evidence"] = str(evidence_path)

        run_llm_step(config, evidence_path, directory, run_id)
        if config.agent_execution == "sequential":
            collect_agent_sequence_paths(directory, paths)
        agents_path = directory / "agent_outputs.json"
        judge_path = directory / "report_judge.json"
        agent_outputs = load_json(agents_path)
        report_judge = load_json(judge_path)
        validate_contract("agent_output.schema.json", agent_outputs)
        validate_contract("report_judge.schema.json", report_judge)
        validate_payload({"agent_outputs": agent_outputs, "report_judge": report_judge}, evidence)
        checks.append(check("agentteam_contracts", "AgentTeam contracts", "ok", "Agent outputs and report judge validated.", f"{agents_path}; {judge_path}"))
        paths["agent_outputs"] = str(agents_path)
        paths["report_judge"] = str(judge_path)

        report_paths = write_reports(evidence, agent_outputs, report_judge, directory / "reports")
        checks.append(check("report_generation", "Report generation", "ok", f"{len(report_paths)} report file(s) generated.", str(directory / "reports")))
        paths["reports_dir"] = str(directory / "reports")

        if config.publish_reports:
            published_paths = write_reports(evidence, agent_outputs, report_judge, ROOT / "reports" / config.bucket)
            checks.append(check("report_publish_copy", "Report publish copy", "ok", f"{len(published_paths)} report file(s) copied to reports/{config.bucket}.", str(ROOT / "reports" / config.bucket)))
            paths["published_reports_dir"] = str(ROOT / "reports" / config.bucket)

        scan_paths = [Path(value) for value in paths.values() if Path(value).is_file()]
        scan_paths.extend(report_paths)
        assert_no_secret_leak(scan_paths, secrets)
        checks.append(check("secret_leak", "Secret leak check", "ok", "No loaded secret value found in core artifacts."))

        health = health_payload(
            config=config,
            run_id=run_id,
            status="ok",
            summary="Pipeline completed: raw, normalized, Evidence, AgentTeam, reports, and quality gates succeeded.",
            checks=checks,
            evidence_count=len(evidence),
            agent_success=4,
            agent_failed=0,
            report_outputs=len(report_paths),
        )
        write_json(health_path, health)
        validate_contract("health.schema.json", health)
        paths["health"] = str(health_path)

        manifest = {
            "schema_version": "research_pipeline_manifest_v1",
            "run_id": run_id,
            "run_at": now_jst(),
            "target_id": config.target_id,
            "date": date,
            "bucket": config.bucket,
            "provider": config.provider,
            "model": config.model,
            "agent_execution": config.agent_execution,
            "codex_reasoning_effort": config.codex_reasoning_effort if config.provider == "codex_cli" else None,
            "loaded_env_keys": sorted(loaded_keys),
            "paths": paths,
            "status": "ok",
        }
        write_json(manifest_path, manifest)
        return manifest
    except Exception as exc:
        if config.agent_execution == "sequential":
            collect_agent_sequence_paths(directory, paths)
        checks.append(check("pipeline_error", "Pipeline error", "error", str(exc)))
        health = health_payload(
            config=config,
            run_id=run_id,
            status="error",
            summary="Pipeline failed; inspect pipeline_manifest.json and health.json.",
            checks=checks,
            evidence_count=evidence_count_so_far,
            agent_success=0,
            agent_failed=1,
            report_outputs=0,
        )
        write_json(health_path, health)
        write_json(
            manifest_path,
            {
                "schema_version": "research_pipeline_manifest_v1",
                "run_id": run_id,
                "run_at": now_jst(),
                "target_id": config.target_id,
                "date": date,
                "bucket": config.bucket,
                "provider": config.provider,
                "model": config.model,
                "agent_execution": config.agent_execution,
                "paths": {**paths, "health": str(health_path)},
                "status": "error",
                "error": str(exc),
            },
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run J-Quants -> Evidence -> AgentTeam -> report into runs/.")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--code", required=True, help="J-Quants issue code, e.g. 86970.")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--bucket", default="morning", choices=["morning", "close", "research"])
    parser.add_argument("--market", default="")
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--provider", default="codex_cli", choices=["mock", "codex_cli", "openai_api", "anthropic_api", "gemini_api"])
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--codex-reasoning-effort", default="low")
    parser.add_argument("--codex-timeout", type=int, default=600, help="Per Codex CLI call timeout passed to Agent runners.")
    parser.add_argument("--agent-timeout", type=int, default=0, help="Whole Agent runner subprocess timeout. Defaults to codex-timeout * step count + 120.")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--out-root", type=Path, default=ROOT / "runs")
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--history-raw", action="append", default=[], type=Path, help="Additional J-Quants raw artifact for multi-day indicators. Can be repeated.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--save-prompt", action="store_true")
    parser.add_argument("--save-raw-response", action="store_true")
    parser.add_argument("--resume-agent-sequence", action="store_true", help="When using sequential Agents, reuse valid existing agent_steps/*.json.")
    parser.add_argument("--no-publish-reports", action="store_true")
    parser.add_argument("--include-edinet", action="store_true")
    parser.add_argument("--edinet-raw", type=Path)
    parser.add_argument("--edinet-type", default="2")
    parser.add_argument("--agent-execution", choices=["combined", "sequential"], default="combined")
    parser.add_argument("--no-derived-indicators", action="store_true")
    parser.add_argument("--include-news", action="store_true")
    parser.add_argument("--news-raw", type=Path)
    parser.add_argument("--news-query", default="")
    parser.add_argument("--news-language", default="en")
    parser.add_argument("--news-rss-url", default="")
    parser.add_argument("--include-ir", action="store_true")
    parser.add_argument("--ir-raw", type=Path)
    parser.add_argument("--ir-url", default="")
    parser.add_argument("--comparison-raw", action="append", default=[], help="Benchmark raw J-Quants artifact as LABEL=path. Can be repeated.")
    parser.add_argument("--comparison-code", action="append", default=[], help="Benchmark J-Quants code to fetch as LABEL=code. Can be repeated.")
    args = parser.parse_args()

    config = PipelineConfig(
        target_id=args.target_id,
        code=args.code,
        stock_code=args.stock_code,
        company_name=args.company_name,
        date=args.date,
        bucket=args.bucket,
        market=args.market,
        themes=tuple(args.theme),
        provider=args.provider,
        model=args.model,
        codex_reasoning_effort=args.codex_reasoning_effort,
        codex_timeout=args.codex_timeout,
        agent_timeout=args.agent_timeout,
        max_attempts=args.max_attempts,
        out_root=args.out_root,
        raw=args.raw,
        history_raws=tuple(args.history_raw),
        env_file=args.env_file,
        timeout=args.timeout,
        save_prompt=args.save_prompt,
        save_raw_response=args.save_raw_response,
        resume_agent_sequence=args.resume_agent_sequence,
        publish_reports=not args.no_publish_reports,
        include_edinet=args.include_edinet,
        edinet_raw=args.edinet_raw,
        edinet_doc_type=args.edinet_type,
        agent_execution=args.agent_execution,
        include_derived_indicators=not args.no_derived_indicators,
        include_news=args.include_news,
        news_raw=args.news_raw,
        news_query=args.news_query,
        news_language=args.news_language,
        news_rss_url=args.news_rss_url,
        include_ir=args.include_ir,
        ir_raw=args.ir_raw,
        ir_url=args.ir_url,
        comparison_raws=tuple(args.comparison_raw),
        comparison_codes=tuple(args.comparison_code),
    )
    manifest = run_pipeline(config)
    print(f"run_id={manifest['run_id']}")
    print(f"run_dir={run_dir(config)}")
    print(f"manifest_path={run_dir(config) / 'pipeline_manifest.json'}")
    print(f"health_path={manifest['paths']['health']}")
    print(f"reports_dir={manifest['paths']['reports_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
