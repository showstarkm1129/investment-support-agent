# Chat Agent Flow

## Purpose

Answer a user question by running one or more analysis agents against existing
evidence. This flow is useful for "what would change the view" or "compare the
bull and bear case" questions.

## Inputs

- user question
- target config
- existing evidence
- optional latest report judge output
- `system/contracts/agent_output.schema.json`
- `system/contracts/chat_judge.schema.json`

## Order

1. `chat_judge` selects the required analysis agents.
2. Selected agents run against existing evidence only.
3. `chat_judge` combines the agent outputs into a user-facing answer.
4. Health records partial failures if a selected agent cannot produce output.

## Outputs

- `runs/{date}/{target_id}/chat/context.json`
- `runs/{date}/{target_id}/chat/manifest.json`
- optional `runs/{date}/{target_id}/chat/agent_outputs.json`
- `runs/{date}/{target_id}/chat/chat_judge.json`

## Boundaries

- Do not run connectors.
- Do not create new evidence unless the flow escalates to `chat_research`.
- Do not convert an agent stance into a trade recommendation or investment instruction.
