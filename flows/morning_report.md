# Morning Report Flow

## Purpose

Build a pre-market view before the Tokyo market opens. The output should state
what changed overnight, what is still unknown, and which evidence matters for
the target. It must not produce trade instructions.

## Inputs

- `config/app.example.json` or production app config
- `config/targets.example.json`
- `config/sources.example.json`
- latest relevant artifacts from `runs/*/{target_id}/close/`
- connector outputs under `data/raw/` and `data/normalized/`
- schemas under `contracts/`

## Order

1. `search_design` defines the morning search plan and source priority.
2. Connectors collect allowed overnight inputs:
   `jquants`, `edinet`, `ir`, `news`, `macro_policy`.
3. `evidence_builder` converts usable facts into `evidence.schema.json`.
4. `bull`, `bear`, `contradiction`, and `pricing` run after evidence is ready.
5. `report_judge` writes `report_judge.schema.json`.
6. Health checks write `health.schema.json`.
7. Report and app generators publish derived artifacts.

## Outputs

- `runs/{date}/{target_id}/morning/context.json`
- `runs/{date}/{target_id}/morning/manifest.json`
- `runs/{date}/{target_id}/morning/evidence.json`
- `runs/{date}/{target_id}/morning/agent_outputs.json`
- `runs/{date}/{target_id}/morning/report_judge.json`
- `runs/{date}/{target_id}/morning/health.json`
- optional generated reports under `reports/morning/`

## Stop Conditions

- Stop before analysis agents if evidence fails the evidence schema.
- Continue with `warn` health status when a noncritical connector is unavailable.
- Mark the report as insufficient information when critical evidence is missing.
