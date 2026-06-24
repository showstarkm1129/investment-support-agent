investment-support-agent/
├─ agents/                         # 各 Agent の役割、禁止事項、判断境界を定義する指示書置き場。
│  ├─ CLAUDE.md
│  ├─ search_design/               # 調査計画と検索方針を決める Agent。
│  ├─ evidence_builder/            # 取得情報を Evidence 形式に整理する Agent。
│  ├─ bull/                        # 強気材料を整理する Agent。
│  ├─ bear/                        # 弱気材料やリスクを整理する Agent。
│  ├─ contradiction/               # 仮説に反する材料や矛盾を探す Agent。
│  ├─ pricing/                     # 材料が価格に織り込まれているかを見る Agent。
│  ├─ report_judge/                # レポート用の最終判断をまとめる Agent。
│  └─ chat_judge/                  # チャット質問の重さに応じて回答経路を選ぶ Agent。
│
├─ flows/                          # 朝・引け後・チャット・調査の実行順を固定する手順書置き場。
│  ├─ README.md
│  ├─ morning_report.md
│  ├─ close_report.md
│  ├─ chat_quick.md
│  ├─ chat_context.md
│  ├─ chat_agent.md
│  ├─ chat_research.md
│  └─ error_policy.md
│
├─ contracts/                      # Agent やスクリプトが読み書きする JSON の正しい形を定義する場所。
│  ├─ README.md
│  ├─ evidence.schema.json
│  ├─ agent_output.schema.json
│  ├─ report_judge.schema.json
│  ├─ chat_judge.schema.json
│  ├─ health.schema.json
│  └─ artifact_contract.md
│
├─ config/                         # 対象銘柄、情報源、実行時設定のサンプル設定置き場。
│  ├─ app.example.json
│  ├─ targets.example.json
│  ├─ sources.example.json
│  └─ runtime.example.json
│
├─ connectors/                     # 外部情報源からデータを取得する処理を分離する場所。
│  ├─ README.md
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
│  ├─ dashboard.html
│  ├─ evidence.html
│  ├─ health.html
│  ├─ agents.html
│  └─ assets/                      # CSS など静的アセット。
│
├─ scripts/                        # レポート生成、画面生成、検証、flow 実行入口のスクリプト置き場。
│  ├─ generate_reports.py
│  ├─ generate_app_pages.py
│  ├─ validate_static.py
│  ├─ run_flow.py
│  └─ prepare_agent_context.py
│
├─ tests/                          # contracts、flow、静的検証のテストを置く場所。
│  ├─ test_contracts.py
│  ├─ test_flow_integrity.py
│  ├─ test_static_validation.py
│  └─ fixtures/                    # テスト用の補助 JSON。
│
├─ docs/                           # 設計、運用、オンボーディングなど人間向け説明資料を置く場所。
│  ├─ architecture.md
│  ├─ operations.md
│  ├─ onboarding_agent_teams.md
│  └─ project_structure.md
│
├─ LICENSE
├─ 要件定義書.md
├─ 会話決定事項メモ.md
├─ 保守検証チェック.md
├─ レポート出力テンプレート案.md
└─ *.html
