# EDINET Connector

Purpose:

- Fetch public filing metadata and documents relevant to a target.
- Surface large-holder reports, securities reports, and timely filing context
  when configured.

Expected raw path:

- `data/raw/edinet/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/edinet/{YYYY-MM-DD}/{target_id}.json`

Failure policy:

- Missing filings are not automatically errors.
- API or parsing failures must be written to health.
