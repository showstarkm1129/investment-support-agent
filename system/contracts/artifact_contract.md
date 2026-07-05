# Artifact Contract

## Run Layout

Each execution writes artifacts below:

`runs/{YYYY-MM-DD}/{target_id}/{bucket}/`

Allowed buckets:

- `morning`
- `close`
- `chat`
- `research`

## Required Files

Every run must write:

- `manifest.json`: run metadata, command, status, and artifact paths.
- `context.json`: target, flow, agents, contracts, and expected inputs/outputs.

Flow-specific files:

- `evidence.json`: must satisfy `system/contracts/evidence.schema.json`.
- `agent_outputs.json`: must satisfy `system/contracts/agent_output.schema.json`.
- `report_judge.json`: must satisfy `system/contracts/report_judge.schema.json`.
- `chat_judge.json`: must satisfy `system/contracts/chat_judge.schema.json`.
- `health.json`: must satisfy `system/contracts/health.schema.json`.

## Derived Outputs

Derived outputs may be copied or generated outside `runs/`:

- `reports/daily/`
- `reports/morning/`
- `reports/weekly/`
- `reports/notebooklm/`
- `app/*.html`

Derived outputs must be reproducible from run artifacts whenever possible.

## Naming

Use stable names inside `runs/`. Use date and target information in published
reports, for example:

- `reports/daily/{YYYY-MM-DD}_{stock_code}_close_analysis.md`
- `reports/daily/{YYYY-MM-DD}_{stock_code}_close_audio.md`
- `reports/daily/{YYYY-MM-DD}_{stock_code}_close.html`

## Retention

Do not mutate past run artifacts. If a run is repeated, create a new `run_id`
inside the same date/target/bucket directory or write a later replacement after
operator approval.
