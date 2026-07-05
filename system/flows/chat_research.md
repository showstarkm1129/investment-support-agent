# Chat Research Flow

## Purpose

Answer a question that needs new information. This is the highest-cost chat
path and must leave a full research trail.

## Inputs

- user question
- target config
- source config
- recent run artifacts for the target
- all contracts needed by collection, evidence, agents, and chat judge

## Order

1. `chat_judge` marks the question as requiring research.
2. `search_design` writes the specific research plan.
3. Allowed connectors collect raw or normalized source material.
4. `evidence_builder` converts usable facts into evidence.
5. Relevant analysis agents run against the updated evidence.
6. `chat_judge` answers with evidence references and research limitations.
7. Health records connector coverage and schema status.

## Outputs

- `runs/{date}/{target_id}/research/context.json`
- `runs/{date}/{target_id}/research/manifest.json`
- `runs/{date}/{target_id}/research/evidence.json`
- optional `runs/{date}/{target_id}/research/agent_outputs.json`
- `runs/{date}/{target_id}/research/chat_judge.json`
- `runs/{date}/{target_id}/research/health.json`

## Stop Conditions

- Stop if collection produces no usable evidence and answer with insufficient
  information.
- Stop if any newly created evidence fails schema validation.
- Continue with caveats when secondary sources are unavailable.
