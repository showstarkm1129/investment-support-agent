# Contributing

このリポジトリは、Agent が同じ入口から実行・検証できる状態を優先します。

## 変更後に走らせるコマンド

```bash
make validate
make test
```

Python を編集した場合:

```bash
make lint-python
```

Markdown を編集した場合:

```bash
make lint-md
make check-links
```

静的画面やレポート生成に関わる変更の場合:

```bash
make reports
make app
make validate-generated
```

## 生成物とキャッシュ

- `__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`node_modules/` はコミットしません。
- API キーや個人設定は `.env` または `config/local.json` に置き、コミットしません。
- `runs/` の過去成果物は監査ログとして扱い、上書きが必要な場合は理由を残します。
- JSON 成果物は `contracts/` の schema に合わせ、`make validate-contracts` または `make check-artifacts` で確認します。
