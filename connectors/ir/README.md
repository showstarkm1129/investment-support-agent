# IR Connector

Purpose:

- Collect official company IR releases, presentation pages, and result material.
- Preserve source URLs and publication timestamps.

Expected raw path:

- `data/raw/ir/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/ir/{YYYY-MM-DD}/{target_id}.json`

Fetch official IR page metadata:

```bash
python3 connectors/ir/fetch_page.py \
  --target-id TARGET-SAMPLE-8697 \
  --company-name "日本取引所グループ" \
  --url "https://www.jpx.co.jp/corporate/investor-relations/" \
  --date 2025-03-28
```

Build Evidence:

```bash
python3 connectors/ir/build_evidence.py \
  --raw data/raw/ir/2025-03-28/TARGET-SAMPLE-8697/<raw-file>.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/ir_evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ" \
  --date 2025-03-28
```

Reliability:

- Official company material normally maps to source reliability `A`.
- The evidence directness still depends on how directly the material affects
  the tracked hypothesis.
