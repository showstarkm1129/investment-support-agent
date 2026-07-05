# Operations

## Daily Close Run

1. Confirm target and source config.
2. Run `scripts/run_flow.py --flow close_report --target-id TARGET-SAMPLE-6501`.
3. Confirm `manifest.json` and `context.json` were created under `runs/`.
4. Run collection and Agent Teams using the generated context.
5. Validate artifacts against `system/contracts/`.
6. Generate reports and app pages.
7. Review health warnings before publishing.

## Morning Run

Use `morning_report` when the goal is pre-market context. It should reuse the
latest close run when useful and explicitly mark overnight gaps.

## Chat Runs

Start with `chat_quick` or `chat_context`. Escalate to `chat_agent` or
`chat_research` only when the question needs more reasoning or new facts.

## API Keys And Local Secrets

API keys should be stored in a machine-local env file, not in prompts, flow
scripts, or committed config.

1. Copy `.env.example` to `.env`.
2. Fill only the keys you actually use, for example `OPENAI_API_KEY` or `JQUANTS_API_KEY`.
3. Run API flows with `scripts/run_flow.py --provider openai_api --mode live`.

`.env`, `.env.*`, and `system/config/local.json` are ignored by Git. `run_flow.py`
loads `.env` by default, or the file specified by `system/config/local.json`:

```json
{
  "schema_version": "local_config_v1",
  "env_file": ".env"
}
```

You can also pass an explicit file:

```bash
python3 scripts/run_flow.py --script search_design_smoke --provider openai_api --mode live --env-file .env.local
```

Secret values are loaded into the Python process environment only. They are not
written to prompts, `context.json`, `manifest.json`, `agent_trace.json`, or LLM
response files. The manifest may record key names such as `OPENAI_API_KEY` for
auditability, but not the values.

For J-Quants, prefer the current API V2 key from the dashboard:

```env
JQUANTS_API_KEY=
```

Legacy token-auth fields are still present in `.env.example` for old flows, but
Google SSO users should normally leave these blank unless a legacy connector
explicitly requires them:

```env
JQUANTS_EMAIL=
JQUANTS_PASSWORD=
JQUANTS_REFRESH_TOKEN=
```

## J-Quants To AgentTeam Smoke

Use this path when you want to test the data-to-report pipeline without giving
Agents direct access to secrets.

For production-shaped experiments, prefer the one-command pipeline. It writes
raw, normalized, Evidence, Agent outputs, Judge output, health, manifest, and
reports under `runs/YYYY-MM-DD/{target_id}/{bucket}/`.

```bash
python3 scripts/run_research_pipeline.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28 \
  --bucket morning \
  --market prime \
  --theme 取引所 \
  --agent-execution sequential \
  --provider codex_cli \
  --model gpt-5.4-mini \
  --codex-reasoning-effort low \
  --include-edinet
```

The `codex_cli` provider runs Codex through:

```bash
codex exec -m gpt-5.4-mini -c model_reasoning_effort=low
```

Use `--codex-timeout` to cap each Codex CLI call and `--agent-timeout` to cap
the whole Agent runner subprocess. If `--agent-timeout` is omitted, the
pipeline derives a cap from the Codex timeout and the selected execution mode.

Use `--provider mock --model deterministic-baseline` for a no-cost pipeline
smoke. Use `--raw`, `--edinet-raw`, `--news-raw`, or `--ir-raw` to replay saved
connector artifacts without calling external data APIs.

News collection can be enabled with NewsAPI when `NEWS_API_KEY` is configured:

```bash
python3 scripts/run_research_pipeline.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28 \
  --include-news \
  --news-query '"Japan Exchange Group" OR JPX' \
  --agent-execution sequential
```

Use `--news-raw` to replay saved NewsAPI raw JSON without calling the external
API. News Evidence stores title, source, URL, publication time, summary, and a
short excerpt only; it does not scrape or store full article text.

Official IR page collection can be enabled with `--include-ir`. This stores
page metadata and a short snippet only; it does not store full page text in
Evidence.

```bash
python3 scripts/run_research_pipeline.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28 \
  --include-ir \
  --ir-url "https://www.jpx.co.jp/corporate/investor-relations/" \
  --agent-execution sequential
```

Derived J-Quants indicators are included by default. With one daily record the
pipeline adds intraday indicators such as open-to-close change, daily range,
and close position. When the normalized input contains enough daily records it
also adds moving averages and volume ratios. Pass `--no-derived-indicators` to
disable this Evidence.

Relative benchmark or sector comparison can be added with saved raw artifacts
or fetchable J-Quants issue codes:

```bash
python3 scripts/run_research_pipeline.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28 \
  --comparison-raw SectorETF=runs/2025-03-28/SECTOR-ETF/morning/raw/jquants/2025-03-28/SECTOR-ETF/daily_quotes_13060_20250328_raw.json \
  --agent-execution sequential
```

`--comparison-code LABEL=CODE` fetches the comparison raw artifact through
J-Quants during the run. Use this for sector ETFs or other benchmark proxies
available through the same daily quotes endpoint.

To calculate moving averages from saved raw artifacts, pass additional raw
files with `--history-raw`:

```bash
python3 scripts/run_research_pipeline.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28 \
  --raw runs/2025-03-28/TARGET-SAMPLE-8697/morning/raw/jquants/2025-03-28/TARGET-SAMPLE-8697/daily_quotes_86970_20250328_raw.json \
  --history-raw runs/2025-03-24/TARGET-SAMPLE-8697/morning/raw/jquants/2025-03-24/TARGET-SAMPLE-8697/daily_quotes_86970_20250324_raw.json \
  --history-raw runs/2025-03-25/TARGET-SAMPLE-8697/morning/raw/jquants/2025-03-25/TARGET-SAMPLE-8697/daily_quotes_86970_20250325_raw.json \
  --provider mock \
  --agent-execution sequential
```

`--agent-execution sequential` runs the production-like chain:

```text
search_design -> evidence_builder -> bull -> bear -> contradiction -> pricing -> report_judge
```

Each step writes its own JSON under `agent_steps/`. Later Agents receive prior
step outputs in their prompt. If a step returns invalid JSON, an unknown
Evidence ID, or a schema-incompatible artifact, the runner writes
`*_failure_attempt_XX.json` and retries with a repair prompt.

When a sequential run fails after one or more step outputs have already been
written, rerun the same pipeline command with `--resume-agent-sequence`. Valid
existing `agent_steps/{step}.json` files are reused and marked as `skipped` in
`agent_sequence_health.json`; the first missing or invalid step is run again.
The pipeline-level `health.json` remains the overall run health, while
`agent_sequence_health.json` preserves Agent-chain-specific checks.

During long Codex CLI runs, inspect `agent_sequence_status.json` to see
`current_step`, `failed_step`, completed steps, resumed steps, and per-Agent
statuses. This file is updated before and after each Agent step, so it is the
fastest way to tell whether the run is progressing, waiting on a specific
Agent, or ready to resume after a failure.

For a concise terminal summary, run:

```bash
python3 scripts/show_run_status.py \
  --run-dir runs/2025-03-28/TARGET-SAMPLE-8697/morning
```

You can also point it at `pipeline_manifest.json`:

```bash
python3 scripts/show_run_status.py \
  --manifest runs/2025-03-28/TARGET-SAMPLE-8697/morning/pipeline_manifest.json
```

1. Fetch raw daily quotes:

```bash
python3 connectors/jquants/fetch_daily_quotes.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --date 2025-03-28
```

2. Normalize the raw artifact:

```bash
python3 connectors/jquants/normalize_daily_quotes.py \
  --raw data/raw/jquants/2025-03-28/TARGET-SAMPLE-8697/daily_quotes_86970_20250328_raw.json
```

3. Build Evidence:

```bash
python3 connectors/jquants/build_evidence.py \
  --normalized data/normalized/jquants/2025-03-28/TARGET-SAMPLE-8697.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ"
```

4. Build deterministic AgentTeam readout:

```bash
python3 scripts/build_agent_team_readout.py \
  --evidence runs/2025-03-28/TARGET-SAMPLE-8697/morning/evidence.json \
  --out-dir runs/2025-03-28/TARGET-SAMPLE-8697/morning \
  --target-id TARGET-SAMPLE-8697 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --market prime \
  --theme 取引所 \
  --report-date 2025-03-28
```

5. Optionally run the AgentTeam LLM runner:

```bash
python3 scripts/run_agent_team_llm.py \
  --evidence runs/2025-03-28/TARGET-SAMPLE-8697/morning/evidence.json \
  --out-dir runs/2025-03-28/TARGET-SAMPLE-8697/morning \
  --target-id TARGET-SAMPLE-8697 \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --market prime \
  --theme 取引所 \
  --report-date 2025-03-28 \
  --provider openai_api \
  --model gpt-5.1
```

Use `--provider mock --model deterministic-baseline` for a no-cost smoke test.
The LLM runner writes `agent_outputs.json`, `report_judge.json`, and
`llm_run_manifest.json`. API keys are loaded from `.env`, but only key names are
recorded in the manifest; key values are not written to prompts or artifacts.

6. Generate report files:

```bash
python3 scripts/generate_reports.py \
  --evidence runs/2025-03-28/TARGET-SAMPLE-8697/morning/evidence.json \
  --agents runs/2025-03-28/TARGET-SAMPLE-8697/morning/agent_outputs.json \
  --judge runs/2025-03-28/TARGET-SAMPLE-8697/morning/report_judge.json \
  --out-dir reports/morning
```

## Failure Handling

Keep partial run artifacts. A failed run is still useful when it has a manifest
and health output explaining what failed.
