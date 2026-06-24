# Macro And Policy Connector

Purpose:

- Collect macro, policy, central bank, regulator, and government events that
  may affect the target or its themes.

Expected raw path:

- `data/raw/macro_policy/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/macro_policy/{YYYY-MM-DD}/{target_id}.json`

Usage:

- `search_design` should decide when macro or policy collection is relevant.
- `evidence_builder` should mark indirect macro/policy items with appropriate
  directness and uncertainty.
