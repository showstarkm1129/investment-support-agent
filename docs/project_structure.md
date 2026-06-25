# Project Structure

このドキュメントは、初めてこのプロジェクトを見る人が「どこに何があるか」を素早く把握するための階層図です。

```text
investment-support-agent/
├─ agents/                         # 各 Agent の役割、禁止事項、判断境界を定義する指示書置き場。
│  ├─ AGENTS.md                    # 全 Agent 共通の基本ルール。
│  ├─ search_design/               # 調査計画と検索方針を決める Agent。
│  │  └─ AGENTS.md
│  ├─ evidence_builder/            # 取得情報を Evidence 形式に整理する Agent。
│  │  └─ AGENTS.md
│  ├─ bull/                        # 強気材料を整理する Agent。
│  │  └─ AGENTS.md
│  ├─ bear/                        # 弱気材料やリスクを整理する Agent。
│  │  └─ AGENTS.md
│  ├─ contradiction/               # 仮説に反する材料や矛盾を探す Agent。
│  │  └─ AGENTS.md
│  ├─ pricing/                     # 材料が価格に織り込まれているかを見る Agent。
│  │  └─ AGENTS.md
│  ├─ report_judge/                # レポート用の最終判断をまとめる Agent。
│  │  └─ AGENTS.md
│  └─ chat_judge/                  # チャット質問の重さに応じて回答経路を選ぶ Agent。
│     └─ AGENTS.md
│
├─ flows/                          # 朝・引け後・チャット・調査の実行順を固定する手順書置き場。
│  ├─ README.md                    # flow 全体の考え方と run 保存方針。
│  ├─ morning_report.md            # 朝レポートの実行順。
│  ├─ close_report.md              # 引け後レポートの実行順。
│  ├─ chat_quick.md                # 軽いチャット質問への回答手順。
│  ├─ chat_context.md              # 既存成果物を読んで答えるチャット手順。
│  ├─ chat_agent.md                # 分析 Agent を呼んで答えるチャット手順。
│  ├─ chat_research.md             # 新規調査を伴うチャット手順。
│  └─ error_policy.md              # エラー時や部分失敗時の扱い。
│
├─ contracts/                      # Agent やスクリプトが読み書きする JSON の正しい形を定義する場所。
│  ├─ README.md                    # contract の役割と更新ルール。
│  ├─ evidence.schema.json         # Evidence の JSON Schema。
│  ├─ agent_output.schema.json     # bull/bear など分析 Agent 出力の JSON Schema。
│  ├─ report_judge.schema.json     # レポート判断出力の JSON Schema。
│  ├─ chat_judge.schema.json       # チャット判断出力の JSON Schema。
│  ├─ health.schema.json           # 実行状態・健全性チェック出力の JSON Schema。
│  └─ artifact_contract.md         # runs や reports に保存する成果物の命名・配置ルール。
│
├─ config/                         # 対象銘柄、情報源、実行時設定のサンプル設定置き場。
│  ├─ app.example.json             # アプリ全体の最小設定サンプル。
│  ├─ targets.example.json         # 調査対象銘柄・テーマの設定サンプル。
│  ├─ sources.example.json         # J-Quants、EDINET、IR、News など情報源の設定サンプル。
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
│  ├─ judge_outputs/               # report_judge や chat_judge の出力保存先。
│  ├─ health/                      # 実行状態・健全性チェック結果の保存先。
│  └─ chat_logs/                   # チャット実行ログや会話関連成果物の保存先。
│
├─ runs/                           # 実行ごとの context、manifest、成果物を日付・対象・用途別に保存する場所。
│  ├─ README.md                    # run ディレクトリの保存ルール。
│  └─ YYYY-MM-DD/                  # 実行日の例を示すテンプレート。
│     └─ target_id/                # 対象銘柄や対象テーマごとの保存単位。
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
│  ├─ run_flow.py                  # flow 実行前後の run ディレクトリと manifest/context を管理する入口。
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
│  └─ project_structure.md         # この階層構造説明ドキュメント。
│
├─ LICENSE                         # ライセンス情報。
├─ 要件定義書.md                  # プロジェクトの要件定義。
├─ 会話決定事項メモ.md            # 会話の中で決まった仕様や方針のメモ。
├─ 保守検証チェック.md            # 保守・検証観点のメモ。
├─ レポート出力テンプレート案.md  # レポート出力テンプレートの案。
└─ *.html                          # 初期プロトタイプや構成説明用の HTML。
```

## 読む順番のおすすめ

1. `docs/project_structure.md` で全体像をつかむ。
2. `docs/architecture.md` で処理の流れを理解する。
3. `flows/README.md` と対象 flow を読んで、実行順を確認する。
4. `contracts/README.md` と対象 schema を読んで、入出力の形を確認する。
5. `agents/` の各 `AGENTS.md` を読んで、Agent の役割を確認する。
