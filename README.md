# investment-support-agent

投資判断を「情報収集、証拠化、複数 Agent の分析、Judge による整理、レポート化」まで一貫して扱うための Agent Teams 向けプロジェクトです。

このプロジェクトは売買指示を出すためのものではありません。Evidence と Agent 出力をもとに、情報状況、仮説への影響、不確実性、見方が変わる条件を整理するための土台です。

## 何をするプロジェクトか

対象銘柄やテーマについて、J-Quants、EDINET、IR、News、Macro/Policy などの情報源から材料を集めます。集めた情報は `Evidence` として正規化され、`bull`、`bear`、`contradiction`、`pricing` などの Agent が別々の観点で分析します。最後に `report_judge` や `chat_judge` が、レポートやチャット回答として使える形にまとめます。

処理の安定性を上げるために、役割は次の 3 層に分けています。

- `system/agents/`: 各 Agent の性格、役割、禁止事項を定義します。
- `system/flows/`: 朝、引け後、チャット、調査で誰をどの順番に呼ぶかを定義します。
- `system/contracts/`: Evidence や Agent 出力など、入出力 JSON の正しい形を定義します。

## 初めて読む人向けの順番

1. この `README.md` で全体像をつかむ。
2. [docs/project_structure.md](docs/project_structure.md) で詳細な階層構造を見る。
3. [docs/architecture.md](docs/architecture.md) で処理の流れを確認する。
4. [system/flows/README.md](system/flows/README.md) と使いたい flow を読む。
5. [system/contracts/README.md](system/contracts/README.md) と対象 schema を確認する。
6. [system/agents/AGENTS.md](system/agents/AGENTS.md) と各 Agent の `AGENTS.md` を読む。

## 階層構造

```text
investment-support-agent/
├─ system/agents/                         # 各 Agent の役割、禁止事項、判断境界を定義する指示書置き場。
│  ├─ AGENTS.md                    # 全 Agent 共通の基本ルール。
│  ├─ search_design/               # 調査計画と検索方針を決める Agent。
│  ├─ evidence_builder/            # 取得情報を Evidence 形式に整理する Agent。
│  ├─ bull/                        # 強気材料を整理する Agent。
│  ├─ bear/                        # 弱気材料やリスクを整理する Agent。
│  ├─ contradiction/               # 仮説に反する材料や矛盾を探す Agent。
│  ├─ pricing/                     # 材料が価格に織り込まれているかを見る Agent。
│  ├─ report_judge/                # レポート用の最終判断をまとめる Agent。
│  └─ chat_judge/                  # チャット質問の重さに応じて回答経路を選ぶ Agent。
│
├─ system/flows/                          # 朝・引け後・チャット・調査の実行順を固定する手順書置き場。
│  ├─ README.md                    # flow 全体の考え方と run 保存方針。
│  ├─ morning_report.md            # 朝レポートの実行順。
│  ├─ close_report.md              # 引け後レポートの実行順。
│  ├─ chat_quick.md                # 軽いチャット質問への回答手順。
│  ├─ chat_context.md              # 既存成果物を読んで答えるチャット手順。
│  ├─ chat_agent.md                # 分析 Agent を呼んで答えるチャット手順。
│  ├─ chat_research.md             # 新規調査を伴うチャット手順。
│  └─ error_policy.md              # エラー時や部分失敗時の扱い。
│
├─ system/contracts/                      # Agent やスクリプトが読み書きする JSON の正しい形を定義する場所。
│  ├─ README.md                    # contract の役割と更新ルール。
│  ├─ evidence.schema.json         # Evidence の JSON Schema。
│  ├─ agent_output.schema.json     # 分析 Agent 出力の JSON Schema。
│  ├─ report_judge.schema.json     # レポート判断出力の JSON Schema。
│  ├─ chat_judge.schema.json       # チャット判断出力の JSON Schema。
│  ├─ health.schema.json           # 実行状態・健全性チェック出力の JSON Schema。
│  └─ artifact_contract.md         # runs や reports に保存する成果物の命名・配置ルール。
│
├─ system/config/                         # 対象銘柄、情報源、実行時設定のサンプル設定置き場。
│  ├─ app.example.json             # アプリ全体の最小設定サンプル。
│  ├─ targets.example.json         # 調査対象銘柄・テーマの設定サンプル。
│  ├─ sources.example.json         # 情報源の設定サンプル。
│  └─ runtime.example.json         # runs 保存先や検証方針など実行時設定のサンプル。
│
├─ connectors/                     # 外部情報源からデータを取得する処理を分離する場所。
│  ├─ README.md                    # connector 全体の責務と保存先ルール。
│  ├─ jquants/                     # 株価・出来高など J-Quants 系データ取得の置き場。
│  ├─ edinet/                      # EDINET 開示データ取得の置き場。
│  ├─ ir/                          # 企業 IR 情報取得の置き場。
│  ├─ news/                        # ニュース取得の置き場。
│  └─ macro_policy/                # マクロ・政策イベント取得の置き場。
│
├─ data/                           # サンプル、取得済みデータ、正規化データ、Agent 出力を保存する場所。
│  ├─ sample/                      # 画面やレポート生成に使うサンプル JSON。
│  ├─ raw/                         # connector が取得した生データ。
│  ├─ normalized/                  # 生データを扱いやすく正規化したデータ。
│  ├─ evidence/                    # Evidence 化されたデータの保存先。
│  ├─ agent_outputs/               # 分析 Agent の出力保存先。
│  ├─ judge_outputs/               # Judge Agent の出力保存先。
│  ├─ health/                      # 実行状態・健全性チェック結果の保存先。
│  └─ chat_logs/                   # チャット実行ログや会話関連成果物の保存先。
│
├─ runs/                           # 実行ごとの context、manifest、成果物を日付・対象・用途別に保存する場所。
│  └─ YYYY-MM-DD/
│     └─ target_id/
│        ├─ morning/               # 朝レポート実行の成果物。
│        ├─ close/                 # 引け後レポート実行の成果物。
│        ├─ chat/                  # チャット回答実行の成果物。
│        └─ research/              # 新規調査を伴う実行の成果物。
│
├─ reports/                        # Markdown や HTML として生成されたレポートを保存する場所。
│  ├─ daily/                       # 日次・引け後レポート。
│  ├─ morning/                     # 朝レポート。
│  ├─ weekly/                      # 週次レポート。
│  └─ notebooklm/                  # NotebookLM などに渡しやすい形式の出力。
│
├─ app/                            # 静的 HTML のダッシュボードや確認画面を置く場所。
│  ├─ dashboard.html               # 全体の判断状況を見る画面。
│  ├─ evidence.html                # Evidence を確認する画面。
│  ├─ health.html                  # 実行状態やエラー状況を見る画面。
│  ├─ agents.html                  # Agent 指示書への入口画面。
│  └─ assets/                      # CSS など静的アセット。
│
├─ scripts/                        # レポート生成、画面生成、検証、flow 実行入口のスクリプト置き場。
│  ├─ generate_reports.py          # sample JSON から Markdown/HTML レポートを生成する。
│  ├─ generate_app_pages.py        # sample JSON から app の HTML 画面を生成する。
│  ├─ validate_static.py           # 構成、JSON、リンク、生成物の静的検証を行う。
│  ├─ run_flow.py                  # run ディレクトリと manifest/context を管理する入口。
│  └─ prepare_agent_context.py     # Agent Teams に渡す context.json を作成する。
│
├─ tests/                          # contracts、flow、静的検証のテストを置く場所。
│  ├─ test_contracts.py            # サンプル JSON が schema に合うか確認する。
│  ├─ test_flow_integrity.py       # flow 文書と run_flow の整合性を確認する。
│  ├─ test_static_validation.py    # validate_static.py が通るか確認する。
│  └─ fixtures/                    # テスト用の補助 JSON。
│
├─ docs/                           # 設計、運用、オンボーディングなど人間向け説明資料を置く場所。
│  ├─ architecture.md              # 全体アーキテクチャの説明。
│  ├─ operations.md                # 日次運用や障害時対応の説明。
│  ├─ onboarding_agent_teams.md    # Agent Teams に作業を渡すための説明。
│  └─ project_structure.md         # より詳しい階層構造説明。
│
├─ LICENSE                         # ライセンス情報。
├─ docs/planning/要件定義書.md                  # プロジェクトの要件定義。
├─ docs/planning/会話決定事項メモ.md            # 会話の中で決まった仕様や方針のメモ。
├─ docs/planning/保守検証チェック.md            # 保守・検証観点のメモ。
├─ docs/planning/レポート出力テンプレート案.md  # レポート出力テンプレートの案。
└─ *.html                          # 初期プロトタイプや構成説明用の HTML。
```

## 基本的な使い方

よく使う入口は `Makefile` にまとめています。迷った場合は [docs/ai_commands.md](docs/ai_commands.md) の順に実行してください。

### 静的検証

```bash
make validate
```

生成済みレポートや画面との差分まで確認する場合:

```bash
make validate-generated
```

### テスト

```bash
make test
```

### flow 実行準備

Agent Teams に渡す `context.json` と実行記録用の `manifest.json` を作成します。

```bash
make flow FLOW=close_report TARGET=TARGET-SAMPLE-6501
```

作成先の例:

```text
runs/{YYYY-MM-DD}/TARGET-SAMPLE-6501/close/
├─ context.json
└─ manifest.json
```

### サンプルからレポート生成

```bash
make reports
```

### サンプルからアプリ画面生成

```bash
make app
```

## 重要な考え方

- Evidence は判断材料の最小単位です。
- Agent は Evidence をもとに、特定の観点だけを担当します。
- Judge は複数 Agent の出力をまとめ、情報状況と不確実性を明示します。
- Flow は実行順を固定し、毎回のブレを減らします。
- Contract は入出力の形を固定し、後続処理や画面生成を壊れにくくします。
- Run は実行ごとの記録を残し、後から追跡できるようにします。

## 生成物の位置づけ

- `data/sample/` は開発・画面確認用のサンプルです。
- `runs/` は実行単位の監査ログです。
- `reports/` は人間が読むための公開・共有用出力です。
- `app/` は静的 HTML として確認するための画面です。

## 注意

このプロジェクトの出力は、投資助言や売買推奨ではありません。事実、証拠、仮説への影響、不確実性、追加確認すべき情報を整理するための支援材料として扱ってください。
