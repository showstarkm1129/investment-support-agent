#!/usr/bin/env python3
"""Generate MVP report artifacts from canonical JSON files.

This is the first thin vertical slice:
Evidence JSON + Agent JSON + Report Judge JSON
  -> detailed Markdown
  -> audio Markdown
  -> simple HTML report
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


LABELS = {
    "upside_evidence_leading": "上方向材料優勢",
    "downside_evidence_leading": "下方向材料優勢",
    "mixed": "材料拮抗",
    "insufficient_information": "情報不足",
    "no_material_change": "大きな変化なし",
    "supportive": "補強",
    "slightly_supportive": "やや補強",
    "neutral": "中立",
    "slightly_negative": "やや悪化",
    "negative": "悪化",
    "undetermined": "整理不能",
    "slightly_upside": "やや上方向",
    "upside": "上方向",
    "slightly_downside": "やや下方向",
    "downside": "下方向",
    "pending": "保留",
    "priced_in": "織り込み",
    "high": "高",
    "medium": "中",
    "low": "低",
    "unread": "未読",
    "reviewed": "確認済み",
    "ignored": "無視",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def label(value: str | None) -> str:
    if value is None:
        return ""
    return LABELS.get(value, value)


def yen(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}円"


def audio_metric_text(key: str, value: Any) -> str:
    labels = {
        "close": "終値",
        "change_pct": "前日比",
        "volume_ratio_20d": "20日平均比出来高",
        "turnover_yen": "売買代金",
        "contract_period_years": "契約期間",
        "change_3d_pct": "3営業日騰落率",
        "close_position": "終値位置",
    }
    label_text = labels.get(key, key)
    if key == "close":
        return f"{label_text}: {yen(value)}"
    if key in {"change_pct", "change_3d_pct"}:
        return f"{label_text}: {value:+.1f}%"
    if key == "volume_ratio_20d":
        return f"{label_text}: {value:.1f}倍"
    if key == "turnover_yen":
        return f"{label_text}: {value / 100_000_000:.0f}億円"
    if key == "contract_period_years":
        return f"{label_text}: {value}年"
    return f"{label_text}: {value}"


def evidence_by_id(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["evidence_id"]: item for item in evidence}


def markdown_evidence_item(item: dict[str, Any]) -> str:
    content = item["content"]
    source = item["source"]
    evaluation = item["evaluation"]
    metrics = content.get("metrics", {})
    metric_lines = []
    for key, value in metrics.items():
        metric_lines.append(f"- {key}: {value}")
    metrics_md = "\n".join(metric_lines) if metric_lines else "- 重要数値なし"

    return f"""### {item["evidence_id"]}: {content["title"]}

- source_type: {source["source_type"]}
- source_reliability: {source["source_reliability"]}
- directness: {label(evaluation["directness"])}
- freshness: {label(evaluation["freshness"])}
- impact_level: {label(evaluation["impact_level"])}
- direction_hint: {label(evaluation["direction_hint"])}

要約:
{content["summary"]}

重要数値:

{metrics_md}

仮説への影響:
{evaluation["hypothesis_impact"]}
"""


def build_analysis_markdown(
    evidence: list[dict[str, Any]],
    agent_bundle: dict[str, Any],
    judge: dict[str, Any],
) -> str:
    target = judge["target"]
    market_readout = judge["market_readout"]
    info = judge["information_status"]
    hypo = judge["hypothesis_impact"]
    uncertainty = judge["uncertainty"]
    weights = judge["evidence_weight"]
    used = judge["used_evidence"]
    ev_map = evidence_by_id(evidence)

    important_evidence = []
    for used_item in used:
        ev = ev_map.get(used_item["evidence_id"])
        if ev:
            important_evidence.append(markdown_evidence_item(ev))

    agent_sections = []
    for agent in agent_bundle["agent_outputs"]:
        agent_sections.append(
            f"""### {agent["agent_name"]}

- claim_strength: {agent["claim_strength"]}
- confidence: {label(agent["confidence"])}

結論:
{agent["conclusion"]}

根拠:
{", ".join(agent.get("evidence_ids", [])) or "該当Evidenceなし"}

重要ポイント:
{chr(10).join(f"- {point}" for point in agent.get("key_points", []))}

限界:
{chr(10).join(f"- {item}" for item in agent.get("limitations", [])) or "- 特記事項なし"}
"""
        )

    view_conditions = "\n".join(
        f"- 条件: {item['condition']}\n  - 影響: {item['effect']}\n  - 関連仮説: {item['related_hypothesis']}"
        for item in judge["view_change_conditions"]
    )
    missing = "\n".join(
        f"- {item['item']}: {item['reason']}" for item in judge["missing_information"]
    )

    return f"""# 日次詳細レポート: {target["stock_code"]} {target["company_name"]}

- レポート種別: 引け後
- 対象日: {agent_bundle["report_date"]}
- 対象銘柄: {target["stock_code"]} {target["company_name"]}
- 市場: {target["market"]}
- 生成時刻: {judge["run_at"]}

## 1. 今日の一言結論

{market_readout["summary"]}

## 2. 材料整理サマリー

- 材料の読み: {label(market_readout["label"])}
- 材料バランス: {market_readout["evidence_balance_score"]:+}
- confidence: {label(market_readout["confidence"])}
- 情報状態: {label(info["label"])}
- 仮説への影響: {label(hypo["label"])}
- 不確実性: {label(uncertainty["level"])}

## 3. 情報状態

{info["summary"]}

## 4. 中期仮説への影響

{hypo["summary"]}

## 5. 証拠重み

| 方向 | 重み |
|---|---:|
| 上方向材料 | {weights["upside"]}% |
| 下方向材料 | {weights["downside"]}% |
| 反証 | {weights["contradiction"]}% |
| 織り込み | {weights["priced_in"]}% |

## 6. 重要Evidence

{chr(10).join(important_evidence)}

## 7. Agent別の見方

{chr(10).join(agent_sections)}

## 8. 不確実性・未確認情報

{missing}

## 9. 見方が変わる条件

{view_conditions}
"""


def audio_evidence_item(item: dict[str, Any], reason: str) -> str:
    content = item["content"]
    source = item["source"]
    evaluation = item["evaluation"]
    metrics = content.get("metrics", {})
    metrics_text = "、".join(audio_metric_text(key, value) for key, value in metrics.items())
    if not metrics_text:
        metrics_text = "明示的な数値なし"
    return f"""### {content["title"]}

- 要約: {content["summary"]}
- 採用理由: {reason}
- 情報源: {source["source_type"]} / {source["source_name"]} / 信頼度{source["source_reliability"]}
- 評価: 方向は{label(evaluation["direction_hint"])}、直接性は{label(evaluation["directness"])}、鮮度は{label(evaluation["freshness"])}、影響度は{label(evaluation["impact_level"])}
- 重要数値: {metrics_text}
- 仮説への影響: {evaluation["hypothesis_impact"]}
"""


def build_audio_markdown(
    evidence: list[dict[str, Any]],
    agent_bundle: dict[str, Any],
    judge: dict[str, Any],
) -> str:
    target = judge["target"]
    market_readout = judge["market_readout"]
    info = judge["information_status"]
    hypo = judge["hypothesis_impact"]
    uncertainty = judge["uncertainty"]
    ev_map = evidence_by_id(evidence)
    evidence_points = []
    for used in judge["used_evidence"]:
        ev = ev_map.get(used["evidence_id"])
        if ev:
            evidence_points.append(audio_evidence_item(ev, used["reason"]))
    agent_points = "\n".join(
        f"""### {agent["agent_name"]}

- 結論: {agent["conclusion"]}
- 根拠Evidence: {", ".join(agent.get("evidence_ids", [])) or "該当Evidenceなし"}
- 重要ポイント: {"、".join(agent.get("key_points", [])) or "特記事項なし"}
- 限界: {"、".join(agent.get("limitations", [])) or "特記事項なし"}
"""
        for agent in agent_bundle["agent_outputs"]
    )
    missing = "\n".join(
        f"- {item['item']}: {item['reason']}" for item in judge["missing_information"]
    )
    uncertainty_factors = "\n".join(f"- {factor}" for factor in uncertainty.get("factors", []))
    conditions = "。".join(
        f"{item['condition']}場合、{item['effect']}"
        for item in judge["view_change_conditions"][:2]
    )

    return f"""# 音声ブリーフ: {target["stock_code"]} {target["company_name"]}

## 今日の一言

今日は、{target["company_name"]}について、{label(info["label"])}です。
材料バランスは{market_readout["evidence_balance_score"]:+}、材料の読みは{label(market_readout["label"])}、confidenceは{label(market_readout["confidence"])}です。

## 情報状態

{info["summary"]}

この見方の中心は、上方向材料の重みが{judge["evidence_weight"]["upside"]}%で最も大きい一方、短期過熱や未確認情報も残っている点です。
つまり、材料の傾きは上方向寄りですが、まだ断定ではありません。

## 中期仮説への影響

{hypo["summary"]}

## 根拠になったEvidence

{chr(10).join(evidence_points)}

## Agent別の理由

{agent_points}

## 不確実性

不確実性は{label(uncertainty["level"])}です。
主な不確実性は次の通りです。

{uncertainty_factors}

未確認情報と、それを確認する理由は次の通りです。

{missing}

## 見方が変わる条件

{conditions}。

## まとめ

このブリーフは売買行動の提案ではありません。
対象銘柄に関する事実、証拠、仮説への影響、不確実性を整理したものです。
"""


def report_nav(report_href: str) -> str:
    items = [
        ("dashboard", "Dashboard", "../../app/dashboard.html", "green"),
        ("evidence", "Evidence", "../../app/evidence.html", "blue"),
        ("report", "Report", report_href, "green"),
        ("health", "Health", "../../app/health.html", "amber"),
        ("flow", "Flow", "../../app/flow_builder.html", "red"),
        ("agents", "Agent指示書", "../../app/agents.html", "blue"),
    ]
    links = []
    for key, text, href, color in items:
        active_class = " active" if key == "report" else ""
        links.append(
            f'<a class="nav-link{active_class}" href="{href}"><i class="dot {color}"></i><span>{text}</span></a>'
        )
    return f"""
      <aside class="nav">
        <div class="brand">
          <b>AI投資情報OS</b>
          <span>MVP connected UI</span>
        </div>
        <nav class="nav-links">
          {''.join(links)}
        </nav>
        <div class="theme-switch" aria-label="テーマ切替">
          <button class="theme-button" type="button" data-theme-value="light" aria-pressed="true">White</button>
          <button class="theme-button" type="button" data-theme-value="dark" aria-pressed="false">Dark</button>
        </div>
      </aside>
    """


def theme_script() -> str:
    return """
  <script>
    (() => {
      const storageKey = "investment-support-agent-theme";
      const root = document.documentElement;
      const initialTheme = localStorage.getItem(storageKey) || "light";

      const applyTheme = (theme) => {
        root.dataset.theme = theme;
        document.querySelectorAll("[data-theme-value]").forEach((button) => {
          button.setAttribute("aria-pressed", String(button.dataset.themeValue === theme));
        });
      };

      applyTheme(initialTheme);

      window.addEventListener("DOMContentLoaded", () => {
        applyTheme(localStorage.getItem(storageKey) || initialTheme);
        document.querySelectorAll("[data-theme-value]").forEach((button) => {
          button.addEventListener("click", () => {
            const theme = button.dataset.themeValue || "light";
            localStorage.setItem(storageKey, theme);
            applyTheme(theme);
          });
        });
      });
    })();
  </script>
"""


def build_html_report(
    evidence: list[dict[str, Any]],
    agent_bundle: dict[str, Any],
    judge: dict[str, Any],
) -> str:
    target = judge["target"]
    market_readout = judge["market_readout"]
    info = judge["information_status"]
    hypo = judge["hypothesis_impact"]
    uncertainty = judge["uncertainty"]
    weights = judge["evidence_weight"]
    report_href = f"{agent_bundle['report_date']}_{target['stock_code']}_close.html"
    ev_map = evidence_by_id(evidence)
    evidence_cards = []
    for used in judge["used_evidence"]:
        ev = ev_map.get(used["evidence_id"])
        if not ev:
            continue
        content = ev["content"]
        evaluation = ev["evaluation"]
        evidence_cards.append(
            f"""
            <article class="card">
              <div class="meta">{html.escape(ev['identity']['published_at'][:10])} / {html.escape(ev['source']['source_type'])}</div>
              <h3>{html.escape(content['title'])}</h3>
              <p>{html.escape(content['summary'])}</p>
              <div class="chips">
                <span class="chip">信頼{html.escape(ev['source']['source_reliability'])}</span>
                <span class="chip">直接 {html.escape(label(evaluation['directness']))}</span>
                <span class="chip">新鮮 {html.escape(label(evaluation['freshness']))}</span>
                <span class="chip">影響 {html.escape(label(evaluation['impact_level']))}</span>
                <span class="chip">{html.escape(label(evaluation['direction_hint']))}</span>
              </div>
            </article>
            """
        )

    conditions = "".join(
        f"<li><b>{html.escape(item['condition'])}</b><br>{html.escape(item['effect'])}</li>"
        for item in judge["view_change_conditions"]
    )
    missing = "".join(
        f"<li><b>{html.escape(item['item'])}</b><br>{html.escape(item['reason'])}</li>"
        for item in judge["missing_information"]
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(target["company_name"])} 引け後レポート</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="../../app/assets/app.css">
  {theme_script()}
</head>
<body>
  <div class="app">
    {report_nav(report_href)}
    <main>
  <section class="panel">
    <div class="muted">{html.escape(judge["run_at"])} / 引け後</div>
    <h1>{html.escape(target["stock_code"])} {html.escape(target["company_name"])} 日次レポート</h1>
    <p>{html.escape(market_readout["summary"])}</p>
  </section>

  <section class="grid-4">
    <div class="panel"><div class="muted">材料の読み</div><div class="value">{html.escape(label(market_readout["label"]))}</div></div>
    <div class="panel"><div class="muted">材料バランス</div><div class="value">{market_readout["evidence_balance_score"]:+}</div></div>
    <div class="panel"><div class="muted">confidence</div><div class="value">{html.escape(label(market_readout["confidence"]))}</div></div>
    <div class="panel"><div class="muted">不確実性</div><div class="value">{html.escape(label(uncertainty["level"]))}</div></div>
  </section>

  <section class="panel">
    <h2>情報状態</h2>
    <p><b>{html.escape(label(info["label"]))}</b>: {html.escape(info["summary"])}</p>
  </section>

  <section class="panel">
    <h2>中期仮説への影響</h2>
    <p><b>{html.escape(label(hypo["label"]))}</b>: {html.escape(hypo["summary"])}</p>
  </section>

  <section class="panel">
    <h2>証拠重み</h2>
    <p>上方向材料 {weights["upside"]}% / 下方向材料 {weights["downside"]}% / 反証 {weights["contradiction"]}% / 織り込み {weights["priced_in"]}%</p>
  </section>

  <section class="panel">
    <h2>重要Evidence</h2>
    <div class="evidence-list">
      {''.join(evidence_cards)}
    </div>
  </section>

  <section class="panel">
    <h2>未確認情報</h2>
    <ul>{missing}</ul>
  </section>

  <section class="panel">
    <h2>見方が変わる条件</h2>
    <ul>{conditions}</ul>
  </section>
    </main>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("data/sample/evidence.json"))
    parser.add_argument("--agents", type=Path, default=Path("data/sample/agent_outputs.json"))
    parser.add_argument("--judge", type=Path, default=Path("data/sample/report_judge.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/daily"))
    args = parser.parse_args()

    evidence = load_json(args.evidence)
    agent_bundle = load_json(args.agents)
    judge = load_json(args.judge)

    target = judge["target"]
    report_date = agent_bundle["report_date"]
    prefix = f"{report_date}_{target['stock_code']}_close"
    args.out_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        f"{prefix}_analysis.md": build_analysis_markdown(evidence, agent_bundle, judge),
        f"{prefix}_audio.md": build_audio_markdown(evidence, agent_bundle, judge),
        f"{prefix}.html": build_html_report(evidence, agent_bundle, judge),
    }

    for filename, content in outputs.items():
        path = args.out_dir / filename
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
