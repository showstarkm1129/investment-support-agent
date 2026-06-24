# Runs

Run artifacts are stored by date, target, and bucket:

`runs/{YYYY-MM-DD}/{target_id}/{morning|close|chat|research}/`

The committed `YYYY-MM-DD/target_id/` tree is a template that documents the
shape expected by `scripts/run_flow.py`.

Generated runs should keep:

- `manifest.json`
- `context.json`
- flow-specific outputs such as `evidence.json`, `agent_outputs.json`,
  `report_judge.json`, `chat_judge.json`, and `health.json`
