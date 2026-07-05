# Agent Team Flows

This directory fixes the execution order for Agent Teams.

The project has three separate control layers:

- `system/agents/`: role, tone, prohibitions, and decision boundaries for each agent.
- `system/flows/`: when each agent or connector is called.
- `system/contracts/`: what each stage must read and write.

Flow names map to run directories:

| Flow | Run bucket | Primary output |
| --- | --- | --- |
| `morning_report` | `morning` | pre-market report package |
| `close_report` | `close` | after-close report package |
| `chat_quick` | `chat` | low-latency answer |
| `chat_context` | `chat` | context-aware answer from existing artifacts |
| `chat_agent` | `chat` | answer with one or more analysis agents |
| `chat_research` | `research` | answer after new collection and evidence build |

Common run lifecycle:

1. `scripts/run_flow.py` creates `runs/{date}/{target_id}/{bucket}/`.
2. `scripts/prepare_agent_context.py` writes `context.json`.
3. Connectors collect raw or normalized inputs when the flow allows collection.
4. Agents write outputs that match the schemas in `system/contracts/`.
5. Judge and health artifacts are written.
6. Report and app generators may publish derived views.

Every flow must keep a complete trail in `runs/`. Do not overwrite a past run
unless the operator intentionally deletes it first.
