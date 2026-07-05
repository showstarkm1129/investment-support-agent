# EDINET Connector

Purpose:

- Fetch public filing metadata and documents relevant to a target.
- Surface large-holder reports, securities reports, and timely filing context
  when configured.

Expected raw path:

- `data/raw/edinet/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/edinet/{YYYY-MM-DD}/{target_id}.json`

Daily documents smoke:

```bash
python3 connectors/edinet/fetch_documents.py \
  --target-id TARGET-SAMPLE-8697 \
  --date 2025-03-28
```

Build Evidence from EDINET document metadata:

```bash
python3 connectors/edinet/build_evidence.py \
  --raw data/raw/edinet/2025-03-28/TARGET-SAMPLE-8697/documents_2025-03-28_raw.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/edinet_evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --sec-code 8697
```

Failure policy:

- Missing filings are not automatically errors.
- API or parsing failures must be written to health.
