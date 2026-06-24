# News Connector

Purpose:

- Collect public news items relevant to a target or theme.
- Preserve title, source, URL, publication time, and short snippet.

Expected raw path:

- `data/raw/news/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/news/{YYYY-MM-DD}/{target_id}.json`

Boundaries:

- Do not scrape paywalled content unless the operator has configured a legal
  access method.
- Do not treat unsourced commentary as high-reliability evidence.
