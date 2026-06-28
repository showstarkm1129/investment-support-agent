# AI Commands

## 全体検証

```bash
make validate
make test
```

## 契約と成果物

```bash
make validate-contracts
make validate-flow-scripts
make check-artifacts
```

## レポート生成

```bash
make reports
```

## 静的画面生成

```bash
make app
```

## Flow 実行

```bash
make flow FLOW=close_report TARGET=TARGET-SAMPLE-6501
make flow-script SCRIPT=semiconductor_sector_morning MODE=simulate
```

## Python/Markdown/Playwright

```bash
make lint-python
make lint-md
make test-e2e
```
