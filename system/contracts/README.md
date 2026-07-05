# Contracts

Contracts define the stable shape of Agent Team artifacts.

Required contracts:

- `evidence.schema.json`: normalized facts from source material.
- `agent_output.schema.json`: outputs from bull, bear, contradiction, and
  pricing agents.
- `report_judge.schema.json`: final daily or close report readout.
- `chat_judge.schema.json`: chat answer and routing decision.
- `health.schema.json`: runtime and data-quality status.
- `artifact_contract.md`: path and naming conventions for generated artifacts.

Agents may be rewritten. Connectors may change. The contract files should move
slowly, because downstream reports, app pages, tests, and audit workflows depend
on them.

When a contract changes:

1. Add a new schema version.
2. Update sample data or fixtures.
3. Update `scripts/validate_static.py`.
4. Update flow documents if the execution order or artifact names changed.
