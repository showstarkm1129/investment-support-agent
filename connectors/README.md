# Connectors

Connectors isolate external collection from Agent Team reasoning.

Connector responsibilities:

- Collect raw source data without making investment judgements.
- Save raw files under `data/raw/{connector}/` when available.
- Save normalized records under `data/normalized/{connector}/` when parsing is
  deterministic.
- Return enough metadata for `evidence_builder` to create evidence.
- Report failures to health instead of hiding them.

Connector outputs are inputs, not evidence. Only `evidence_builder` writes
objects that satisfy `contracts/evidence.schema.json`.

Initial connector folders:

- `jquants/`: price, volume, listing, and market data.
- `edinet/`: public filings and disclosure metadata.
- `ir/`: company IR pages, releases, and presentations.
- `news/`: public news and market commentary sources.
- `macro_policy/`: central bank, government, regulator, and macro events.
