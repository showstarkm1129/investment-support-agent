# J-Quants Connector

Purpose:

- Fetch target price, volume, listing, and market data.
- Normalize fields used by price and pricing agents.

Authentication:

- Prefer J-Quants API V2 API key authentication.
- Store the key in `.env` as `JQUANTS_API_KEY`.
- Send the key as an `x-api-key` request header from connector code.
- Do not put the API key in flow scripts, prompts, run artifacts, or committed config.
- `JQUANTS_EMAIL`, `JQUANTS_PASSWORD`, and `JQUANTS_REFRESH_TOKEN` are legacy
  token-auth settings and should only be used for old V1-style flows if needed.

Expected raw path:

- `data/raw/jquants/{YYYY-MM-DD}/{target_id}/`

Daily quotes smoke:

```bash
python3 connectors/jquants/fetch_daily_quotes.py \
  --target-id TARGET-SAMPLE-8697 \
  --code 86970 \
  --date 2025-03-28
```

Output example:

```text
data/raw/jquants/2025-03-28/TARGET-SAMPLE-8697/daily_quotes_86970_20250328_raw.json
```

On failure, the connector writes an `*_error.json` artifact in the same layout
with a redacted request URL and error details.

Expected normalized path:

- `data/normalized/jquants/{YYYY-MM-DD}/{target_id}.json`

Normalize a raw daily quotes artifact:

```bash
python3 connectors/jquants/normalize_daily_quotes.py \
  --raw data/raw/jquants/2025-03-28/TARGET-SAMPLE-8697/daily_quotes_86970_20250328_raw.json
```

Build a multi-day normalized history from saved raw artifacts:

```bash
python3 connectors/jquants/build_history.py \
  --raw "data/raw/jquants/2025-03-*/TARGET-SAMPLE-8697/*_raw.json" \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/normalized/jquants/history.json
```

Build Evidence from normalized daily quotes:

```bash
python3 connectors/jquants/build_evidence.py \
  --normalized data/normalized/jquants/2025-03-28/TARGET-SAMPLE-8697.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ"
```

Build derived indicators and Evidence:

```bash
python3 connectors/jquants/build_indicators.py \
  --normalized data/normalized/jquants/2025-03-28/TARGET-SAMPLE-8697.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/jquants_indicators.json \
  --evidence-out runs/2025-03-28/TARGET-SAMPLE-8697/morning/jquants_indicator_evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ"
```

Build relative benchmark/sector comparison and Evidence:

```bash
python3 connectors/jquants/build_relative_comparison.py \
  --target-normalized data/normalized/jquants/2025-03-28/TARGET-SAMPLE-8697.json \
  --benchmark SectorETF=data/normalized/jquants/2025-03-28/SECTOR-ETF.json \
  --out runs/2025-03-28/TARGET-SAMPLE-8697/morning/jquants_relative_comparison.json \
  --evidence-out runs/2025-03-28/TARGET-SAMPLE-8697/morning/jquants_relative_comparison_evidence.json \
  --stock-code 8697 \
  --company-name "日本取引所グループ"
```

Evidence ownership:

- `fetch_daily_quotes.py` writes raw J-Quants artifacts.
- `normalize_daily_quotes.py` converts raw artifacts into normalized daily quote records.
- `build_evidence.py` converts normalized records into `system/contracts/evidence.schema.json`
  compatible Evidence.
- `build_indicators.py` derives price/volume indicators such as intraday change,
  daily range, moving averages when enough records exist, and volume ratios.
- `build_relative_comparison.py` compares the target against benchmark or
  sector-proxy normalized records and emits market-context Evidence.
- Downstream AgentTeam scripts consume the Evidence file and do not need direct
  access to the J-Quants API key.
