# Chat Quick Flow

## Purpose

Answer lightweight user questions with minimal latency. Use only already-loaded
or already-generated artifacts. Do not collect new information.

## Inputs

- user question
- current target
- selected evidence, current judge output, or current dashboard state
- `system/contracts/chat_judge.schema.json`

## Order

1. `chat_judge` classifies the question as quick.
2. `chat_judge` reads only the selected or current artifacts.
3. `chat_judge` answers with evidence references and caveats.
4. Health is updated only when the runtime has enough context to do so cheaply.

## Outputs

- `runs/{date}/{target_id}/chat/context.json`
- `runs/{date}/{target_id}/chat/manifest.json`
- `runs/{date}/{target_id}/chat/chat_judge.json`

## Escalation

- Escalate to `chat_context` when the answer requires broader run context.
- Escalate to `chat_agent` when the user asks for a stance comparison.
- Escalate to `chat_research` when new facts are required.
