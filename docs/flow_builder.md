# Flow Builder

Flow Builder は、Agent Team 風の実行スクリプトを UI から選択、作成、実行するためのローカル操作画面です。

## 半導体セクタースクリプト

最初のサンプルは次のファイルです。

```text
config/flow_scripts/semiconductor_sector_morning.json
```

このスクリプトは、半導体セクターを対象に次の順番で Agent を動かす想定です。

1. `search_design`
2. `connector:jquants`, `connector:ir`, `connector:news`, `connector:macro_policy`
3. `evidence_builder`
4. `bull`, `bear`, `contradiction`, `pricing`
5. `report_judge`, `health`

## コマンドで試す

```bash
python scripts/run_flow.py --script semiconductor_sector_morning --mode simulate
```

モデルを明示したい場合は `--model` を付けます。

```bash
python scripts/run_flow.py --script semiconductor_sector_morning --provider codex --model gpt-5-codex --mode simulate
```

## サブスク枠のCLIで使う

ChatGPT / Claude のサブスク枠で使いたい場合は、API provider ではなく CLI provider を使います。

```text
provider: codex  -> Codex CLI
provider: claude -> Claude Code CLI
```

Flow Script では次のように指定します。

```json
{
  "provider": "codex",
  "model": "default",
  "mode": "simulate"
}
```

`mode=live` にすると、`agent_trace.json` の各 prompt を順番に CLI へ渡します。Codex CLI の場合は、CLI側で ChatGPT アカウントにログイン済みならサブスク枠の利用経路になります。APIキーを使う provider とは料金経路が違います。

```bash
python scripts/run_flow.py --script semiconductor_sector_morning --provider codex --model gpt-5-codex --mode live
```

## API provider

API経由で実行したい場合は provider を切り替えます。

```text
openai_api    -> OPENAI_API_KEY
anthropic_api -> ANTHROPIC_API_KEY
gemini_api    -> GEMINI_API_KEY
```

例:

```bash
python scripts/run_flow.py --script semiconductor_sector_morning --provider openai_api --model gpt-5.1 --mode live
```

API provider は基本的に従量課金です。レスポンスは `runs/.../llm_responses/` に保存されます。

生成先は次の形です。

```text
runs/{YYYY-MM-DD}/SECTOR-SEMICONDUCTOR/morning/
├─ context.json
├─ manifest.json
├─ agent_trace.json
├─ prompts/
├─ llm_responses/
├─ evidence.json
├─ agent_outputs.json
├─ report_judge.json
└─ health.json
```

`simulate` は外部データ取得や LLM 実行を行わず、Agent の動き方、プロンプト、成果物の置き場を確認するためのモードです。

## UIで試す

```bash
python scripts/flow_server.py
```

起動後、次の URL を開きます。

```text
http://127.0.0.1:8765/flow_builder.html
```

UI では次を操作できます。

- 手動実行するスクリプトの選択
- `codex` / `claude` / `manual` の選択
- `prepare` / `dry-run` / `simulate` の選択
- 毎朝サーチなどが参照するスクリプトの選択
- フォーム入力から新しい Flow Script JSON を作成

## 自動サーチ設定

自動サーチが参照するスクリプトは次のファイルで管理します。

```text
config/auto_search.example.json
```

まだ scheduler は実装していません。このファイルは、Windows Task Scheduler や cron からどの Flow Script を呼ぶかを決めるための参照設定です。
