# Close Report Flow

## Purpose

Build the after-close report from market data, disclosures, IR, news, and
policy signals available by the close-report window. This is the main daily
artifact for review and later chat answers.

## Inputs

- target config and source config
- same-day price and volume data
- same-day disclosures, IR releases, news, and macro/policy events
- previous run artifacts for the target
- schemas under `system/contracts/`

## Order

1. `search_design` creates the close-report collection plan.
2. Connectors collect close-window inputs:
   `jquants`, `edinet`, `ir`, `news`, `macro_policy`.
3. `evidence_builder` writes canonical evidence.
4. `bull`, `bear`, `contradiction`, and `pricing` run in parallel.
5. `report_judge` combines the agent outputs and evidence.
6. Health checks record source, processing, and output status.
7. `generate_reports.py` and `generate_app_pages.py` publish derived views.

## Outputs

- `runs/{date}/{target_id}/close/context.json`
- `runs/{date}/{target_id}/close/manifest.json`
- `runs/{date}/{target_id}/close/evidence.json`
- `runs/{date}/{target_id}/close/agent_outputs.json`
- `runs/{date}/{target_id}/close/report_judge.json`
- `runs/{date}/{target_id}/close/health.json`
- generated files under `reports/daily/` and `app/`

## Stop Conditions

- Stop before `report_judge` if any required analysis-agent output is missing.
- Continue with explicit uncertainty when price data exists but disclosure data
  is incomplete.
- Never hide connector failures; surface them in health output.
