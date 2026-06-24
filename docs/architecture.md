# Architecture

The system is organized around a stable artifact pipeline:

1. Config selects targets, sources, schedules, and runtime behavior.
2. Connectors collect source material.
3. `evidence_builder` turns source material into evidence.
4. Analysis agents produce stance-specific outputs.
5. Judge agents create report or chat decisions.
6. Health checks record source and processing status.
7. Generators publish reports and static app pages.

The key design rule is separation of concerns:

- Connectors fetch.
- Evidence builder normalizes.
- Analysis agents reason from evidence.
- Judges synthesize.
- Generators publish.

This keeps Agent Teams predictable and makes each artifact auditable.
