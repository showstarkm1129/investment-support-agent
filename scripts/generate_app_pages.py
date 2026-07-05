#!/usr/bin/env python3
"""Generate connected MVP UI pages from the sample JSON data."""

from __future__ import annotations

import argparse
import html
from pathlib import Path
from typing import Any

from generate_reports import label, load_json


STATUS_LABELS = {
    "ok": "正常",
    "warn": "注意",
    "error": "エラー",
    "info": "情報",
    "skipped": "未実行",
}

AGENT_LABELS = {
    "bull": "上方向材料Agent",
    "bear": "下方向材料Agent",
    "contradiction": "反証Agent",
    "pricing": "織り込みAgent",
}

AGENT_DOCS = [
    ("共通指示", "../system/agents/AGENTS.md", "全Agent共通の禁止事項、根拠ルール、出力方針。"),
    ("探索設計Agent", "../system/agents/search_design/AGENTS.md", "銘柄やテーマから何を調べるべきかを設計する。"),
    ("証拠化Agent", "../system/agents/evidence_builder/AGENTS.md", "取得素材をEvidenceカードへ整える。"),
    ("上方向材料Agent", "../system/agents/bull/AGENTS.md", "中期仮説を補強する事実を整理する。"),
    ("下方向材料Agent", "../system/agents/bear/AGENTS.md", "中期仮説を弱める事実や過熱リスクを整理する。"),
    ("反証Agent", "../system/agents/contradiction/AGENTS.md", "仮説の前提を壊し得る事実を探す。"),
    ("織り込みAgent", "../system/agents/pricing/AGENTS.md", "材料の価格反映と短期過熱を整理する。"),
    ("Report Judge", "../system/agents/report_judge/AGENTS.md", "定型レポートの最終情報整理を行う。"),
    ("Chat Judge", "../system/agents/chat_judge/AGENTS.md", "質問の重さに応じて情報とAgentを振り分ける。"),
]


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def date_only(value: str | None) -> str:
    if not value:
        return "-"
    return value[:10]


def time_only(value: str | None) -> str:
    if not value or "T" not in value:
        return "-"
    return value.split("T", 1)[1][:5]


def status_class(status: str) -> str:
    return {
        "ok": "status-ok",
        "warn": "status-warn",
        "error": "status-error",
        "info": "status-info",
        "skipped": "status-info",
    }.get(status, "status-info")


def format_metric(key: str, value: Any) -> str:
    if key == "close":
        return f"{value:,.0f}円"
    if key in {"change_pct", "change_3d_pct"}:
        return f"{value:+.1f}%"
    if key == "volume_ratio_20d":
        return f"{value:.1f}倍"
    if key == "turnover_yen":
        return f"{value / 100_000_000:.0f}億円"
    if key == "contract_period_years":
        return f"{value}年"
    return str(value)


def metric_label(key: str) -> str:
    return {
        "close": "終値",
        "change_pct": "前日比",
        "volume_ratio_20d": "出来高比",
        "turnover_yen": "売買代金",
        "contract_period_years": "契約期間",
        "change_3d_pct": "3日騰落",
        "close_position": "終値位置",
    }.get(key, key)


def metrics_html(metrics: dict[str, Any]) -> str:
    if not metrics:
        return '<span class="metric">重要数値 <b>なし</b></span>'
    return "".join(
        f'<span class="metric">{esc(metric_label(key))} <b>{esc(format_metric(key, value))}</b></span>'
        for key, value in metrics.items()
    )


def quality_line(item: dict[str, Any]) -> str:
    source = item["source"]
    evaluation = item["evaluation"]
    direction = label(evaluation.get("direction_hint"))
    direction_class = "green"
    if evaluation.get("direction_hint") in {"priced_in", "neutral", "unknown"}:
        direction_class = "blue"
    if evaluation.get("direction_hint") in {"downside", "contradiction"}:
        direction_class = "red"
    impact_class = "green" if evaluation["impact_level"] == "high" else "amber"
    return f"""
      <div class="quality-line">
        <span class="badge green">信頼{esc(source["source_reliability"])}</span>
        <span class="badge green">直接 {esc(label(evaluation["directness"]))}</span>
        <span class="badge green">新鮮 {esc(label(evaluation["freshness"]))}</span>
        <span class="badge {impact_class}">影響 {esc(label(evaluation["impact_level"]))}</span>
        <span class="quality-separator">|</span>
        <span class="badge {direction_class}">{esc(direction)}</span>
      </div>
    """


def nav(active: str) -> str:
    items = [
        ("dashboard", "Dashboard", "dashboard.html", "green"),
        ("evidence", "Evidence", "evidence.html", "blue"),
        ("report", "Report", "../reports/daily/2026-06-22_6501_close.html", "green"),
        ("health", "Health", "health.html", "amber"),
        ("flow", "Flow", "flow_builder.html", "red"),
        ("agents", "Agent指示書", "agents.html", "blue"),
    ]
    links = []
    for key, text, href, color in items:
        active_class = " active" if key == active else ""
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


def page(title: str, active: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="assets/app.css">
  {theme_script()}
</head>
<body>
  <div class="app">
    {nav(active)}
    <main>
      {content}
    </main>
  </div>
</body>
</html>
"""


def evidence_map(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["evidence_id"]: item for item in evidence}


def evidence_card(item: dict[str, Any], selected: bool = False) -> str:
    content = item["content"]
    identity = item["identity"]
    source = item["source"]
    published_date = date_only(identity.get("published_at"))
    published_time = time_only(identity.get("published_at"))
    collected_time = time_only(identity.get("collected_at"))
    selected_class = " selected" if selected else ""
    return f"""
      <article class="card{selected_class}" id="{esc(item["evidence_id"])}">
        <div class="card-top">
          <div>
            <div class="meta">
              <span>{esc(published_date)}</span>
              <span>{esc(source["source_type"])}</span>
              <span>{esc(source["source_name"])}</span>
              <span>{esc(published_time)}発表 / {esc(collected_time)}取得</span>
            </div>
            <div class="title-row">
              <a class="title" href="evidence.html#{esc(item["evidence_id"])}">{esc(content["title"])}</a>
              <button class="ask-icon" aria-label="この記事へ質問">?</button>
            </div>
          </div>
          {quality_line(item)}
        </div>
        <p class="summary">{esc(content["summary"])}</p>
        <div class="metrics">{metrics_html(content.get("metrics", {}))}</div>
      </article>
    """


def build_dashboard(
    evidence: list[dict[str, Any]],
    agents: dict[str, Any],
    judge: dict[str, Any],
    health: dict[str, Any],
) -> str:
    target = judge["target"]
    market_readout = judge["market_readout"]
    info = judge["information_status"]
    hypo = judge["hypothesis_impact"]
    uncertainty = judge["uncertainty"]
    weights = judge["evidence_weight"]
    ev_map = evidence_map(evidence)
    used_cards = [
        evidence_card(ev_map[item["evidence_id"]])
        for item in judge["used_evidence"]
        if item["evidence_id"] in ev_map
    ]
    agent_cards = []
    for item in agents["agent_outputs"]:
        strength = int(item["claim_strength"])
        agent_cards.append(
            f"""
            <article class="card">
              <div class="card-top">
                <div>
                  <h3>{esc(AGENT_LABELS.get(item["agent_name"], item["agent_name"]))}</h3>
                  <p class="muted">{esc(item["stance"])}</p>
                </div>
                <span class="badge blue">強度 {strength}</span>
              </div>
              <p>{esc(item["conclusion"])}</p>
              <div class="bar-track"><div class="bar-fill blue" style="width:{strength}%"></div></div>
            </article>
            """
        )
    health_status = health["overall_status"]
    report_link = "../reports/daily/2026-06-22_6501_close.html"
    audio_link = "../reports/daily/2026-06-22_6501_close_audio.md"
    analysis_link = "../reports/daily/2026-06-22_6501_close_analysis.md"

    return page(
        f'{target["stock_code"]} {target["company_name"]} Dashboard',
        "dashboard",
        f"""
        <div class="topbar">
          <div>
            <h1>Dashboard / 管制塔</h1>
            <p class="subtitle">対象: {esc(target["stock_code"])} {esc(target["company_name"])} / {esc(", ".join(target["themes"]))} / {esc(agents["report_date"])} 引け後</p>
          </div>
        </div>

        <section class="grid-4">
          <div class="stat"><div class="label">情報状態</div><div class="small-value">{esc(label(info["label"]))}</div></div>
          <div class="stat"><div class="label">仮説への影響</div><div class="small-value">{esc(label(hypo["label"]))}</div></div>
          <div class="stat"><div class="label">材料バランス</div><div class="value">{market_readout["evidence_balance_score"]:+}</div></div>
          <div class="stat"><div class="label">不確実性</div><div class="value">{esc(label(uncertainty["level"]))}</div></div>
        </section>

        <section class="panel">
          <div class="topbar">
            <div>
              <h2>出力</h2>
              <p class="muted">生成済みのレポート、Markdown、NotebookLM向け音声用テキストを開きます。</p>
            </div>
            <div class="actions">
              <a class="button" href="{report_link}">HTMLレポート</a>
              <a class="button" href="{analysis_link}">詳細Markdown</a>
              <a class="button" href="{audio_link}">NotebookLM音声用</a>
            </div>
          </div>
        </section>

        <section class="grid-2">
          <div class="panel">
            <h2>今日の情報整理</h2>
            <p><b>{esc(market_readout["summary"])}</b></p>
            <p>{esc(info["summary"])}</p>
            <p class="muted">これは売買行動の提案ではなく、EvidenceとAgent出力に基づく情報整理です。</p>
          </div>
          <div class="panel">
            <h2>証拠重み</h2>
            <div class="bar-list">
              <div class="bar-row"><span>上方向材料</span><div class="bar-track"><div class="bar-fill green" style="width:{weights["upside"]}%"></div></div><b>{weights["upside"]}%</b></div>
              <div class="bar-row"><span>下方向材料</span><div class="bar-track"><div class="bar-fill amber" style="width:{weights["downside"]}%"></div></div><b>{weights["downside"]}%</b></div>
              <div class="bar-row"><span>反証</span><div class="bar-track"><div class="bar-fill red" style="width:{weights["contradiction"]}%"></div></div><b>{weights["contradiction"]}%</b></div>
              <div class="bar-row"><span>織り込み</span><div class="bar-track"><div class="bar-fill blue" style="width:{weights["priced_in"]}%"></div></div><b>{weights["priced_in"]}%</b></div>
            </div>
          </div>
        </section>

        <section class="grid-2">
          <div class="panel">
            <h2>重要Evidence</h2>
            <div class="evidence-list">{''.join(used_cards)}</div>
          </div>
          <div class="panel">
            <h2>見方が変わる条件</h2>
            <div class="evidence-list">
              {''.join(f'<article class="card"><h3>{esc(item["condition"])}</h3><p>{esc(item["effect"])}</p><p class="muted">{esc(item["related_hypothesis"])}</p></article>' for item in judge["view_change_conditions"])}
            </div>
          </div>
        </section>

        <section class="grid-2">
          <div class="panel">
            <h2>Agentの見方</h2>
            <div class="agent-list">{''.join(agent_cards)}</div>
          </div>
          <div class="panel">
            <h2>Chat Judge</h2>
            <p>質問の重さに応じて、呼び出す範囲を変える想定です。</p>
            <div class="chips">
              <span class="chip">Quick</span>
              <span class="chip">Context</span>
              <span class="chip">Agent</span>
              <span class="chip">Research</span>
            </div>
            <div class="detail-section ask-box">
              <div class="ask-row">
                <input value="この材料で見方が変わる条件は？" aria-label="Chat Judgeへの質問">
                <button class="primary">質問</button>
              </div>
              <p class="muted">MVPではUI導線。実回答は次の実装でChat Judgeに接続します。</p>
            </div>
            <div class="detail-section">
              <h3>Health</h3>
              <p>{esc(health["summary"])}</p>
              <span class="status-pill {status_class(health_status)}">{esc(STATUS_LABELS.get(health_status, health_status))}</span>
            </div>
          </div>
        </section>
        """,
    )


def build_evidence_page(evidence: list[dict[str, Any]], judge: dict[str, Any]) -> str:
    target = judge["target"]
    selected = evidence[0]
    detail = selected["content"]
    source = selected["source"]
    workflow = selected["workflow"]
    cards = "".join(evidence_card(item, selected=item is selected) for item in evidence)
    return page(
        "Evidence / 証拠ボード",
        "evidence",
        f"""
        <div class="topbar">
          <div>
            <h1>Evidence / 証拠ボード</h1>
            <p class="subtitle">対象: {esc(target["stock_code"])} {esc(target["company_name"])} / 厳選された材料を高密度で読む画面</p>
          </div>
        </div>

        <section class="grid-4">
          <div class="stat"><div class="label">表示中</div><div class="value">{len(evidence)}</div></div>
          <div class="stat"><div class="label">判断に使用</div><div class="value">{sum(1 for item in evidence if item["workflow"].get("used_in_decision"))}</div></div>
          <div class="stat"><div class="label">未読</div><div class="value">{sum(1 for item in evidence if item["workflow"].get("human_review_status") == "unread")}</div></div>
          <div class="stat"><div class="label">重要度高</div><div class="value">{sum(1 for item in evidence if item["evaluation"].get("impact_level") == "high")}</div></div>
        </section>

        <section class="layout-evidence">
          <details class="panel filters">
            <summary>
              <span class="filter-label">フィルタ</span>
              <span class="badge blue">5</span>
            </summary>
            <div class="filter-body">
              <h3>検索</h3>
              <input value="AI サーバー 出来高" aria-label="証拠検索">
              <div class="detail-section">
                <h3>状態</h3>
                <div class="chips"><span class="chip">今日追加</span><span class="chip">未読</span><span class="chip">判断に使用</span><span class="chip">後日検証</span></div>
              </div>
              <div class="detail-section">
                <h3>方向</h3>
                <div class="chips"><span class="chip">上方向材料</span><span class="chip">下方向材料</span><span class="chip">反証</span><span class="chip">織り込み</span></div>
              </div>
              <div class="detail-section">
                <h3>証拠品質</h3>
                <div class="chips"><span class="chip">信頼A</span><span class="chip">直接 高</span><span class="chip">新鮮 高</span><span class="chip">影響 高</span></div>
              </div>
            </div>
          </details>

          <div class="panel">
            <div class="topbar">
              <div>
                <h2>証拠カード</h2>
                <p class="muted">IDなどの管理情報は隠し、日付・見出し・要約を中心に読む設計です。</p>
              </div>
              <div class="detail-header-actions">
                <button class="detail-open-control" type="button" data-detail-open>詳細を表示</button>
                <select aria-label="並び替え">
                  <option>重要度順</option>
                  <option>新しい順</option>
                  <option>未読優先</option>
                </select>
              </div>
            </div>
            <div class="evidence-list">{cards}</div>
          </div>

          <article class="panel evidence-detail" id="evidence-detail">
            <div class="card-top">
              <div>
                <p class="meta"><span>{esc(date_only(selected["identity"].get("published_at")))}</span><span>{esc(source["source_type"])}</span><span>{esc(source["source_name"])}</span></p>
                <h2>{esc(detail["title"])}</h2>
              </div>
              <div class="detail-header-actions">
                <button class="ask-icon" aria-label="この記事へ質問">?</button>
                <button class="icon-button" type="button" aria-label="詳細ペインを閉じる" title="詳細を閉じる" data-detail-close>×</button>
              </div>
            </div>
            {quality_line(selected)}
            <p class="summary">{esc(detail["summary"])}</p>
            <div class="metrics">{metrics_html(detail.get("metrics", {}))}</div>

            <div class="detail-section">
              <h3>この記事で読むべきこと</h3>
              <ul>
                <li>出来高増加と価格維持が同時に出ているため、中期トレンド継続の初期シグナルとして扱える。</li>
                <li>出来高増加の直接理由はまだ完全には特定できていない。</li>
                <li>短期で急騰しているため、織り込みの確認も同時に必要。</li>
              </ul>
            </div>

            <div class="detail-section">
              <h3>AIに質問</h3>
              <div class="ask-box">
                <div class="ask-row">
                  <input value="この出来高増加はどの程度強い根拠？" aria-label="AIへの質問">
                  <button class="primary">質問</button>
                </div>
                <div class="chips">
                  <span class="chip">弱点は？</span>
                  <span class="chip">織り込み済み？</span>
                  <span class="chip">追加で見る情報は？</span>
                </div>
                <p class="muted">この記事への質問はQuick想定。選択中Evidenceと関連Evidenceだけで答えます。</p>
              </div>
            </div>

            <div class="detail-section">
              <h3>人間メモ</h3>
              <textarea>{esc(workflow.get("human_note") or "ここに自分の確認メモを残す。")}</textarea>
              <div class="chips">
                <span class="chip">{esc(label(workflow.get("human_review_status")))}</span>
                <span class="chip">判断に使う: {esc("はい" if workflow.get("used_in_decision") else "いいえ")}</span>
                <span class="chip">後日検証: {esc(workflow.get("review_due_date") or "なし")}</span>
              </div>
            </div>
          </article>
        </section>
        <script>
          (() => {{
            const layout = document.querySelector(".layout-evidence");
            const filters = document.querySelector(".filters");
            const closeButton = document.querySelector("[data-detail-close]");
            const openButton = document.querySelector("[data-detail-open]");
            if (!layout || !filters || !closeButton || !openButton) return;

            const closeDetail = (moveFocus = true) => {{
              layout.classList.add("detail-collapsed");
              if (moveFocus) openButton.focus();
            }};

            closeButton.addEventListener("click", () => {{
              closeDetail();
            }});

            openButton.addEventListener("click", () => {{
              filters.open = false;
              layout.classList.remove("detail-collapsed");
              closeButton.focus();
            }});

            filters.addEventListener("toggle", () => {{
              if (filters.open) closeDetail(false);
            }});
          }})();
        </script>
        """,
    )


def build_health_page(health: dict[str, Any], judge: dict[str, Any]) -> str:
    target = judge["target"]
    section_html = []
    for section in health["sections"]:
        rows = []
        for check in section["checks"]:
            status = check["status"]
            rows.append(
                f"""
                <tr>
                  <td><span class="status-pill {status_class(status)}">{esc(STATUS_LABELS.get(status, status))}</span></td>
                  <td><b>{esc(check["label"])}</b><br><span class="muted">{esc(check["check_id"])}</span></td>
                  <td>{esc(check["message"])}<br><span class="muted">{esc(check["detail"])}</span></td>
                  <td>{esc(check.get("last_run_at") or "-")}</td>
                </tr>
                """
            )
        section_html.append(
            f"""
            <section class="panel">
              <h2>{esc(section["title"])}</h2>
              <table class="table">
                <thead><tr><th>状態</th><th>項目</th><th>内容</th><th>最終実行</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
              </table>
            </section>
            """
        )

    stats = health["stats"]
    overall = health["overall_status"]
    return page(
        "Health / 実行状態",
        "health",
        f"""
        <div class="topbar">
          <div>
            <h1>Health / 実行状態</h1>
            <p class="subtitle">対象: {esc(target["stock_code"])} {esc(target["company_name"])} / 取得・証拠化・Agent・出力の状態</p>
          </div>
        </div>

        <section class="panel">
          <h2>このページで見ること</h2>
          <p>Healthは、レポートがどこまで正しく作られたかを確認する運用チェック画面です。情報取得、Evidence化、Agent分析、Report Judge、NotebookLM用出力までの流れを並べ、失敗や不足があればここで見つけます。</p>
          <div class="grid-3">
            <article class="card">
              <h3>入力が揃ったか</h3>
              <p>価格、IR、ニュースなどの素材取得と、Evidence化の成功・失敗を確認します。</p>
            </article>
            <article class="card">
              <h3>分析が通ったか</h3>
              <p>上方向材料、下方向材料、反証、織り込み、Report Judgeが根拠つきで出力できたかを確認します。</p>
            </article>
            <article class="card">
              <h3>出力できたか</h3>
              <p>Dashboard、Evidence、HTMLレポート、NotebookLM用Markdownが生成されたかを確認します。</p>
            </article>
          </div>
        </section>

        <section class="panel">
          <div class="health-row">
            <span class="status-pill {status_class(overall)}">{esc(STATUS_LABELS.get(overall, overall))}</span>
            <div>
              <h2>現在の状態</h2>
              <p>{esc(health["summary"])}</p>
              <p class="muted">エラーや欠損がある場合も、可能な範囲でレポートを生成し、不足情報として表示します。</p>
            </div>
          </div>
        </section>

        <section class="grid-4">
          <div class="stat"><div class="label">Evidence</div><div class="value">{stats["evidence_total"]}</div></div>
          <div class="stat"><div class="label">使用Evidence</div><div class="value">{stats["evidence_used_in_decision"]}</div></div>
          <div class="stat"><div class="label">Agent成功</div><div class="value">{stats["agent_success"]}</div></div>
          <div class="stat"><div class="label">出力ファイル</div><div class="value">{stats["report_outputs"]}</div></div>
        </section>

        {''.join(section_html)}
        """,
    )


def build_agents_page(judge: dict[str, Any]) -> str:
    target = judge["target"]
    cards = []
    for title, href, description in AGENT_DOCS:
        cards.append(
            f"""
            <article class="card">
              <div class="card-top">
                <div>
                  <h3>{esc(title)}</h3>
                  <p>{esc(description)}</p>
                </div>
                <a class="button" href="{href}">開く</a>
              </div>
            </article>
            """
        )
    return page(
        "Agent指示書",
        "agents",
        f"""
        <div class="topbar">
          <div>
            <h1>Agent指示書</h1>
            <p class="subtitle">対象: {esc(target["stock_code"])} {esc(target["company_name"])} / 各Agentが迷わないためのAGENTS.md一覧</p>
          </div>
        </div>

        <section class="panel">
          <h2>共通ルール</h2>
          <p>このチームは売買行動を提案するのではなく、Evidenceに基づいて情報状態、仮説への影響、不確実性、見方が変わる条件を整理します。</p>
        </section>

        <section class="grid-3">
          {''.join(cards)}
        </section>
        """,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("data/sample/evidence.json"))
    parser.add_argument("--agents", type=Path, default=Path("data/sample/agent_outputs.json"))
    parser.add_argument("--judge", type=Path, default=Path("data/sample/report_judge.json"))
    parser.add_argument("--health", type=Path, default=Path("data/sample/health.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("app"))
    args = parser.parse_args()

    evidence = load_json(args.evidence)
    agents = load_json(args.agents)
    judge = load_json(args.judge)
    health = load_json(args.health)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "dashboard.html": build_dashboard(evidence, agents, judge, health),
        "evidence.html": build_evidence_page(evidence, judge),
        "health.html": build_health_page(health, judge),
        "agents.html": build_agents_page(judge),
    }
    for filename, content in outputs.items():
        path = args.out_dir / filename
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
