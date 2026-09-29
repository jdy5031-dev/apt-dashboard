#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data/apt.db 를 읽어서 휴대폰용 정적 대시보드 docs/index.html 을 만든다.

- 호가: 하루에 여러 번 수집했으면 그날 마지막 스냅샷만 쓴다. 평형(전용 ㎡) 필터를 적용하고
  전용면적 타입(59, 84 …)별로 나눈다. 중복 매물은 네이버가 이미 묶어 준다.
- 실거래: 같은 평형 필터, 해제(취소)된 거래는 뺀다.
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime

from common import DOCS_DIR, area_range, connect, format_price, load_config, setup_logging

log = setup_logging("dashboard")


def area_type(excl_area: float) -> str:
    """전용면적을 타입 이름으로. 59.97 → '59', 84.12 → '84'."""
    return str(int(excl_area))


def asking_series(conn, name: str, lo: float, hi: float) -> dict:
    """{타입: [[날짜, 매물 수, 최저가, 중간값], ...]} (매매 기준)"""
    rows = conn.execute(
        """SELECT substr(s.collected_at, 1, 10) AS day, a.building, a.floor, a.excl_area, a.price
           FROM listing_snapshot s JOIN listing_article a ON a.snapshot_id = s.id
           WHERE s.id IN (SELECT MAX(id) FROM listing_snapshot
                          WHERE complex = ? AND trade_type = 'A1'
                          GROUP BY substr(collected_at, 1, 10))
             AND a.excl_area BETWEEN ? AND ? AND a.price IS NOT NULL""",
        (name, lo, hi),
    ).fetchall()
    by_type_day = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_type_day[area_type(r["excl_area"])][r["day"]].append(r["price"])
    # 매물이 0건인 날도 그래프에 남긴다.
    days = sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT substr(collected_at, 1, 10) FROM listing_snapshot WHERE complex = ? AND trade_type = 'A1'",
        (name,)))
    out = {}
    for t, by_day in by_type_day.items():
        series = []
        for day in days:
            prices = sorted(by_day[day])
            series.append([day, len(prices), prices[0] if prices else None,
                           int(statistics.median(prices)) if prices else None])
        out[t] = series
    return out


def trade_series(conn, name: str, lo: float, hi: float) -> dict:
    """{타입: [[계약일, 금액, 층, 전용㎡], ...]}"""
    rows = conn.execute(
        """SELECT deal_date, price, floor, excl_area FROM trade
           WHERE complex = ? AND cancelled = 0 AND excl_area BETWEEN ? AND ?
           ORDER BY deal_date""",
        (name, lo, hi),
    ).fetchall()
    out = defaultdict(list)
    for r in rows:
        out[area_type(r["excl_area"])].append([r["deal_date"], r["price"], r["floor"], r["excl_area"]])
    return out


def complex_info(conn, name: str) -> dict:
    """{approval: 'YYYY-MM[-DD]', households, far, bcr} — 아직 없으면 빈 dict.
    신축은 사용승인일이 'YYYYMM' 까지만 오기도 하고, 용적률·건폐율이 0(미등록)으로 오기도 한다."""
    r = conn.execute("SELECT * FROM complex_info WHERE complex = ?", (name,)).fetchone()
    if not r:
        return {}
    d = r["use_approval_date"] or ""
    approval = "-".join(p for p in (d[:4], d[4:6], d[6:8]) if p) if len(d) >= 6 else None
    return {"approval": approval, "households": r["households"] or None,
            "far": r["floor_area_ratio"] or None, "bcr": r["building_cov_ratio"] or None}


def build() -> str:
    config = load_config()
    conn = connect()
    complexes = []
    for c in config.get("complexes", []):
        lo, hi = area_range(config, c)
        asking = asking_series(conn, c["name"], lo, hi)
        trades = trade_series(conn, c["name"], lo, hi)
        types = {t: {"asking": asking.get(t, []), "trades": trades.get(t, [])}
                 for t in sorted(set(asking) | set(trades), key=int)}
        complexes.append({"name": c["name"], "info": complex_info(conn, c["name"]), "types": types})
    conn.close()

    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    payload = json.dumps({"updated": updated, "complexes": complexes}, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA__", payload.replace("</", "<\\/")).replace("__UPDATED__", updated)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    log.info("대시보드 생성: %s (단지 %d곳)", out, len(complexes))
    for c in complexes:
        for t, d in c["types"].items():
            last = d["asking"][-1] if d["asking"] else None
            if last:
                log.info("  %s %s㎡: 매물 %d건, 최저 %s, 중간 %s",
                         c["name"], t, last[1], format_price(last[2]), format_price(last[3]))
    return str(out)


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>아파트 시세</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f4f4f1; --surface-1: #fcfcfb; --border: #e3e2dd;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --grid: #ebeae6;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #111110; --surface-1: #1a1a19; --border: #2e2e2c;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e87;
    --grid: #2a2a28;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #111110; --surface-1: #1a1a19; --border: #2e2e2c;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e87;
  --grid: #2a2a28;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
  -webkit-text-size-adjust: 100%;
}
main { max-width: 760px; margin: 0 auto; padding: 16px 16px 48px; }
header h1 { font-size: 20px; margin: 4px 0 2px; }
header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.controls { position: sticky; top: 0; z-index: 2; background: var(--surface-0); padding: 8px 0; margin: 8px 0 4px; }
.toolbar { display: flex; gap: 6px; }
.toolbar + .toolbar { margin-top: 6px; }
.toolbar button { flex: 1; min-height: 36px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--surface-1); color: var(--text-secondary); font: inherit; font-size: 14px; }
.toolbar button[aria-pressed="true"] { border-color: var(--text-primary); color: var(--text-primary); font-weight: 600; }
.table-wrap { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  overflow-x: auto; -webkit-overflow-scrolling: touch; }
.summary { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
.summary th, .summary td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
/* 좌우로 밀어도 단지명은 왼쪽에 고정 */
.summary th:first-child, .summary td:first-child { text-align: left; position: sticky; left: 0; z-index: 1;
  background: var(--surface-1); box-shadow: 1px 0 0 var(--border); }
.summary td small { color: var(--text-muted); font-size: 11px; }
.summary .gap { border-left: 1px solid var(--border); }
.summary th { color: var(--text-muted); font-weight: 500; font-size: 12px; }
.summary tr:last-child td { border-bottom: 0; }
.summary a { color: inherit; text-decoration: none; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 14px 10px; margin-top: 14px; }
.card h2 { font-size: 17px; margin: 0; }
.card .sub { color: var(--text-muted); font-size: 12px; margin: 2px 0 10px; }
.info { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 0 0 12px; padding: 8px 0;
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }
.info div { min-width: 0; }
.info dt { color: var(--text-muted); font-size: 11px; }
.info dd { margin: 0; font-size: 14px; font-weight: 500; }
.info dd small { color: var(--text-muted); font-weight: 400; font-size: 11px; }
@media (max-width: 380px) { .info { grid-template-columns: repeat(2, 1fr); } }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px; }
.stat { min-width: 0; }
.stat .label { color: var(--text-muted); font-size: 12px; }
.stat .value { font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums; }
.stat .note { color: var(--text-secondary); font-size: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.legend span::before { content: ""; display: inline-block; width: 14px; height: 2px; vertical-align: middle;
  margin-right: 5px; background: var(--c); }
.legend span.dash::before { background: repeating-linear-gradient(90deg, var(--c) 0 4px, transparent 4px 7px); }
.legend span.dot::before { width: 8px; height: 8px; border-radius: 50%; }
.chart { position: relative; height: 240px; }
details { margin-top: 8px; font-size: 13px; }
details summary { color: var(--text-secondary); cursor: pointer; padding: 4px 0; }
details table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
details td, details th { padding: 4px 6px; text-align: right; border-bottom: 1px solid var(--border); }
details th { color: var(--text-muted); font-weight: 500; }
.empty { color: var(--text-muted); font-size: 13px; padding: 24px 0; text-align: center; }
</style>
</head>
<body>
<main>
  <header>
    <h1>아파트 시세 추이</h1>
    <p>호가: 네이버 부동산 매매 매물 · 실거래: 국토교통부 · 업데이트 __UPDATED__</p>
  </header>
  <div class="controls">
    <div class="toolbar" id="types" role="group" aria-label="전용면적 타입"></div>
    <div class="toolbar" id="periods" role="group" aria-label="기간">
      <button data-months="6">6개월</button>
      <button data-months="12">1년</button>
      <button data-months="36">3년</button>
      <button data-months="0">전체</button>
    </div>
  </div>
  <div class="table-wrap"><table class="summary" id="summary"></table></div>
  <div id="cards"></div>
</main>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
const DATA = __DATA__;

const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const ts = s => Date.parse(s + "T00:00:00+09:00");
function won(v) {
  if (v == null) return "-";
  const eok = Math.floor(v / 10000), man = v % 10000;
  if (eok && man) return `${eok}억 ${man.toLocaleString()}`;
  return eok ? `${eok}억` : `${man.toLocaleString()}만`;
}
const eokAxis = v => (v / 10000).toFixed(1).replace(/\.0$/, "") + "억";
const ymd = t => { const d = new Date(t); return `${String(d.getFullYear()).slice(2)}.${d.getMonth() + 1}`; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const last = arr => arr && arr.length ? arr[arr.length - 1] : null;

// 비슷한 면적(±3㎡)은 한 버튼으로 묶는다. 예: 59, 60 → 59 / 84, 85 → 84
const typeKeys = [...new Set(DATA.complexes.flatMap(c => Object.keys(c.types)).map(Number))].sort((a, b) => a - b);
const groups = [];
typeKeys.forEach(t => { const g = last(groups); g && t - g[0] <= 3 ? g.push(t) : groups.push([t]); });
const groupOf = t => groups.find(g => g.includes(Number(t)));

let state = {group: 0, months: 12};
try { Object.assign(state, JSON.parse(localStorage.getItem("apt-view") || "{}")); } catch (e) {}
if (!groups[state.group]) state.group = 0;

// 선택한 타입 그룹에 해당하는 단지 데이터(여러 타입이면 첫 타입의 호가 + 전체 실거래)
function view(c) {
  const g = groups[state.group] || [];
  const keys = Object.keys(c.types).filter(t => g.includes(Number(t)));
  if (!keys.length) return null;
  const asking = keys.map(k => c.types[k].asking).sort((a, b) => b.length - a.length)[0];
  const trades = keys.flatMap(k => c.types[k].trades).sort((a, b) => a[0] < b[0] ? -1 : 1);
  return {asking, trades};
}

// 사용승인일·세대수·용적률·건폐율을 표시용 문자열로. 연차는 올해 − 사용승인 연도(네이버 approvalElapsedYear 와 같음).
function infoText(info) {
  info = info || {};
  const ap = info.approval;
  const age = ap ? new Date().getFullYear() - Number(ap.slice(0, 4)) : null;
  return {
    approval: ap ? ap.slice(0, 7).replace("-", ".") : "-",
    age: age != null ? age + "년" : "",
    households: info.households == null ? "-" : info.households.toLocaleString(),
    far: info.far == null ? "-" : info.far + "%",
    bcr: info.bcr == null ? "-" : info.bcr + "%",
  };
}

function renderSummary() {
  const rows = DATA.complexes.map((c, i) => {
    const f = infoText(c.info);
    const info = `<td>${f.approval}${f.age ? ` <small>${f.age}</small>` : ""}</td>
      <td>${f.households}</td><td>${f.far}</td><td>${f.bcr}</td>`;
    const v = view(c);
    if (!v) return `<tr><td>${esc(c.name)}</td>${info}<td class="gap" colspan="3" style="color:var(--text-muted)">${
      Object.keys(c.types).length ? "해당 타입 없음" : "수집 전"}</td></tr>`;
    const a = last(v.asking), t = last(v.trades);
    return `<tr><td><a href="#c${i}">${esc(c.name)}</a></td>${info}
      <td class="gap">${a ? a[1] + "건" : "-"}</td><td>${a ? won(a[2]) : "-"}</td>
      <td>${t ? won(t[1]) : "-"}</td></tr>`;
  }).join("");
  document.getElementById("summary").innerHTML =
    `<thead><tr><th>단지</th><th>사용승인</th><th>세대수</th><th>용적률</th><th>건폐율</th>
      <th class="gap">매물</th><th>최저 호가</th><th>최근 실거래</th></tr></thead><tbody>${rows}</tbody>`;
}

function infoRow(info) {
  if (!info || !Object.keys(info).length) return "";
  const f = infoText(info);
  return `<dl class="info">
    <div><dt>사용승인</dt><dd>${f.approval}${f.age ? ` <small>${f.age}</small>` : ""}</dd></div>
    <div><dt>세대수</dt><dd>${f.households}</dd></div>
    <div><dt>용적률</dt><dd>${f.far}</dd></div>
    <div><dt>건폐율</dt><dd>${f.bcr}</dd></div>
  </dl>`;
}

function renderCards() {
  const root = document.getElementById("cards");
  if (!DATA.complexes.length || !groups.length) {
    root.innerHTML = `<p class="empty">아직 수집된 데이터가 없습니다.</p>`;
    return;
  }
  root.innerHTML = DATA.complexes.map((c, i) => {
    const v = view(c);
    if (!v) return "";
    const a = last(v.asking), t = last(v.trades);
    const types = Object.keys(c.types).filter(k => (groups[state.group] || []).includes(Number(k)));
    const recent = v.trades.slice(-15).reverse().map(r =>
      `<tr><td>${r[0]}</td><td>${won(r[1])}</td><td>${r[2]}층</td><td>${r[3]}㎡</td></tr>`).join("");
    return `<section class="card" id="c${i}">
      <h2>${esc(c.name)}</h2>
      <div class="sub">전용 ${types.join(", ")}㎡</div>
      ${infoRow(c.info)}
      <div class="stats">
        <div class="stat"><div class="label">매물 수</div><div class="value">${a ? a[1] + "건" : "-"}</div>
          <div class="note">${a ? a[0] : ""}</div></div>
        <div class="stat"><div class="label">최저 / 중간 호가</div><div class="value">${a ? won(a[2]) : "-"}</div>
          <div class="note">${a ? "중간 " + won(a[3]) : ""}</div></div>
        <div class="stat"><div class="label">최근 실거래</div><div class="value">${t ? won(t[1]) : "-"}</div>
          <div class="note">${t ? t[0] + " · " + t[2] + "층" : ""}</div></div>
      </div>
      <div class="legend">
        <span style="--c: var(--series-1)">호가 중간값</span>
        <span class="dash" style="--c: var(--series-2)">최저 호가</span>
        <span class="dot" style="--c: var(--series-3)">실거래</span>
      </div>
      <div class="chart"><canvas id="chart${i}" aria-label="${esc(c.name)} 호가와 실거래 추이"></canvas></div>
      <details><summary>최근 실거래 ${v.trades.length ? "(" + Math.min(15, v.trades.length) + "건)" : "없음"}</summary>
        <table><thead><tr><th>계약일</th><th>금액</th><th>층</th><th>전용</th></tr></thead><tbody>${recent}</tbody></table>
      </details>
    </section>`;
  }).join("");
}

const charts = [];
function renderCharts() {
  charts.forEach(ch => ch.destroy());
  charts.length = 0;
  if (!window.Chart) return;
  const minX = state.months ? Date.now() - state.months * 30.44 * 864e5 : -Infinity;
  const grid = css("--grid"), muted = css("--text-muted");
  const s1 = css("--series-1"), s2 = css("--series-2"), s3 = css("--series-3"), surface = css("--surface-1");

  DATA.complexes.forEach((c, i) => {
    const v = view(c), canvas = document.getElementById("chart" + i);
    if (!v || !canvas) return;
    const asking = v.asking.map(r => ({x: ts(r[0]), r})).filter(p => p.x >= minX);
    const trades = v.trades.map(r => ({x: ts(r[0]), y: r[1], r})).filter(p => p.x >= minX);
    const xs = asking.map(p => p.x).concat(trades.map(p => p.x));
    // 데이터가 하루치뿐이면 점이 축 끝에 붙지 않게 앞뒤로 여유를 준다.
    if (xs.length && Math.max(...xs) - Math.min(...xs) < 7 * 864e5) xs.push(Math.min(...xs) - 7 * 864e5, Math.max(...xs) + 7 * 864e5);
    charts.push(new Chart(canvas, {
      data: {datasets: [
        {type: "line", label: "호가 중간값", data: asking.map(p => ({x: p.x, y: p.r[3], r: p.r})),
         borderColor: s1, backgroundColor: s1, borderWidth: 2, pointRadius: asking.length < 3 ? 3 : 0, pointHitRadius: 8},
        {type: "line", label: "최저 호가", data: asking.map(p => ({x: p.x, y: p.r[2], r: p.r})),
         borderColor: s2, backgroundColor: s2, borderWidth: 2, borderDash: [5, 4], pointRadius: asking.length < 3 ? 3 : 0, pointHitRadius: 8},
        {type: "scatter", label: "실거래", data: trades,
         borderColor: surface, backgroundColor: s3, borderWidth: 2, pointRadius: 5, pointHoverRadius: 7, pointHitRadius: 10},
      ]},
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: "nearest", intersect: false},
        plugins: {
          legend: {display: false},
          tooltip: {callbacks: {
            title: items => new Date(items[0].parsed.x).toISOString().slice(0, 10),
            label: item => {
              const r = item.raw.r;
              if (item.dataset.type === "scatter") return `실거래 ${won(r[1])} · ${r[2]}층 · ${r[3]}㎡`;
              return item.datasetIndex === 0 ? `호가 중간 ${won(r[3])} (매물 ${r[1]}건)` : `최저 호가 ${won(r[2])}`;
            },
          }},
        },
        scales: {
          x: {type: "linear", min: xs.length ? Math.min(...xs) : undefined, max: xs.length ? Math.max(...xs) : undefined,
              grid: {display: false}, border: {color: grid},
              ticks: {color: muted, maxTicksLimit: 6, callback: ymd}},
          y: {grid: {color: grid}, border: {display: false},
              ticks: {color: muted, maxTicksLimit: 6, callback: eokAxis}},
        },
      },
    }));
  });
}

function render() {
  document.getElementById("types").innerHTML = groups.map((g, i) =>
    `<button data-group="${i}" aria-pressed="${i === state.group}">${g[0]}㎡</button>`).join("");
  document.querySelectorAll("#periods button").forEach(b =>
    b.setAttribute("aria-pressed", String(Number(b.dataset.months) === state.months)));
  try { localStorage.setItem("apt-view", JSON.stringify(state)); } catch (e) {}
  renderSummary();
  renderCards();
  renderCharts();
}
document.getElementById("types").addEventListener("click", e => {
  const b = e.target.closest("button"); if (b) { state.group = Number(b.dataset.group); render(); }
});
document.getElementById("periods").addEventListener("click", e => {
  const b = e.target.closest("button"); if (b) { state.months = Number(b.dataset.months); render(); }
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderCharts);
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
