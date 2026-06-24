# J-Quants Connector

Purpose:

- Fetch target price, volume, listing, and market data.
- Normalize fields used by price and pricing agents.

Expected raw path:

- `data/raw/jquants/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/jquants/{YYYY-MM-DD}/{target_id}.json`

Evidence ownership:

- This connector does not write evidence directly.
- `evidence_builder` converts normalized records into evidence items.
