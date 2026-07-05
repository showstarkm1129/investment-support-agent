# News Connector

Purpose:

- Collect public news items relevant to a target or theme.
- Preserve title, source, URL, publication time, and short snippet.

Expected raw path:

- `data/raw/news/{YYYY-MM-DD}/{target_id}/`

Expected normalized path:

- `data/normalized/news/{YYYY-MM-DD}/{target_id}.json`

NewsAPI `/v2/everything` smoke:

```bash
python3 connectors/news/fetch_articles.py \
  --target-id TARGET-SAMPLE-8697 \
  --query '"Japan Exchange Group" OR JPX' \
  --date 2025-03-28
```

Build Evidence:

```bash
python3 connectors/news/build_evidence.py \
  --raw data/raw/news/2025-03-28/TARGET-SAMPLE-8697/articles_2025-03-28_raw.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/news_evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ"
```

Boundaries:

- Do not scrape paywalled content unless the operator has configured a legal
  access method.
- Do not treat unsourced commentary as high-reliability evidence.
