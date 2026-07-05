# Agent Task 5: connector:macro_policy

Provider: codex
Model: default
Mode: simulate
Run ID: RUN20260703-SECTOR-SEMICONDUCTOR-MORNING-REPORT
Flow: morning_report
Group: 2

## Script

- script_id: semiconductor_sector_morning
- display_name: 半導体セクター朝サーチ
- depth: normal

## Target

```json
{
  "auto_report_enabled": true,
  "company_name": "半導体セクター",
  "market": "JP-US-watchlist",
  "stock_code": "",
  "target_id": "SECTOR-SEMICONDUCTOR",
  "target_type": "sector",
  "themes": [
    "半導体",
    "生成AI",
    "データセンター",
    "装置",
    "メモリ",
    "規制"
  ],
  "watchlist": [
    {
      "market": "TSE",
      "name": "東京エレクトロン",
      "ticker": "8035"
    },
    {
      "market": "TSE",
      "name": "アドバンテスト",
      "ticker": "6857"
    },
    {
      "market": "TSE",
      "name": "レーザーテック",
      "ticker": "6920"
    },
    {
      "market": "TSE",
      "name": "ディスコ",
      "ticker": "6146"
    },
    {
      "market": "US",
      "name": "NVIDIA",
      "ticker": "NVDA"
    },
    {
      "market": "US",
      "name": "Advanced Micro Devices",
      "ticker": "AMD"
    },
    {
      "market": "US",
      "name": "TSMC",
      "ticker": "TSM"
    },
    {
      "market": "US",
      "name": "ASML",
      "ticker": "ASML"
    }
  ]
}
```

## Instruction Source

connectors/macro_policy/README.md

## Inputs

[
  "search_plan.json"
]

## Required Outputs

[
  "data/raw/macro_policy/{run_id}.json"
]

## Notes

[
  "為替、金利、米中規制、補助金、輸出管理を対象にする。"
]

## Guardrails

- Use evidence IDs when making factual claims.
- Keep facts, interpretation, and uncertainty separate.
- Do not produce trading instructions.
- Write JSON artifacts only when the requested schema and path are clear.
