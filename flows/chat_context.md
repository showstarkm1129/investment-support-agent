# Chat Context Flow

## Purpose

Answer questions by reading existing run artifacts for a target. This flow can
use broader context than `chat_quick`, but still does not collect new data.

## Inputs

- user question
- current target
- recent `evidence.json`, `agent_outputs.json`, `report_judge.json`, and
  `health.json`
- optional prior morning or close runs
- `contracts/chat_judge.schema.json`

## Order

1. `chat_judge` classifies the question as context.
2. `chat_judge` selects relevant existing artifacts.
3. `chat_judge` answers with cited evidence IDs and uncertainty.
4. `chat_judge` records whether research would materially improve the answer.

## Outputs

- `runs/{date}/{target_id}/chat/context.json`
- `runs/{date}/{target_id}/chat/manifest.json`
- `runs/{date}/{target_id}/chat/chat_judge.json`

## Escalation

- Escalate to `chat_agent` when a fresh bull/bear/contradiction/pricing pass is
  needed.
- Escalate to `chat_research` when the current artifacts do not contain enough
  evidence.
