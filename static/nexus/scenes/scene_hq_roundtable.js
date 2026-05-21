import { escapeHtml, normalizeText } from "../utils/presentation.js?v=20260521c";
import { getLayoutHotspots } from "../layout_state.js?v=20260503a";

const HQ_HOTSPOTS = [
  { id: "overview", label: "總覽", x: 0.15, y: 0.2, w: 0.22, h: 0.26, section: "overview" },
  { id: "alerts", label: "警報與風險", x: 0.62, y: 0.18, w: 0.22, h: 0.26, section: "risk" },
  { id: "decision", label: "決策板", x: 0.57, y: 0.64, w: 0.22, h: 0.22, section: "reports" },
  { id: "risk", label: "風險板", x: 0.18, y: 0.58, w: 0.18, h: 0.18, section: "risk" },
  { id: "capital", label: "資金板", x: 0.69, y: 0.56, w: 0.18, h: 0.18, section: "overview" },
  { id: "record", label: "紀錄板", x: 0.43, y: 0.82, w: 0.18, h: 0.14, section: "reports" },
];

function money(value) {
  return `${Number(value || 0).toFixed(2)}U`;
}

function latestMeeting(state) {
  return Array.isArray(state.meetings) && state.meetings.length ? state.meetings[0] : null;
}

function meetingAlerts(state, limit = 5) {
  const meetings = Array.isArray(state.meetings) ? state.meetings : [];
  return meetings.slice(0, limit).map((meeting) => {
    const conclusion = meeting?.conclusion || {};
    const meetingType = String(meeting?.type || "");
    const slot = meeting?.slot || String(meeting?.time || "").slice(11, 16) || "會議";
    return {
      time: meeting?.time || meeting?.created_at || "--",
      level: meetingType === "EMERGENCY_ROUND_TABLE" ? "ALERT_RED" : "INFO",
      summary:
        conclusion.summary ||
        meeting?.summary ||
        `${slot} 圓桌會議已完成，目前沒有摘要文字。`,
      source: "meeting",
    };
  });
}

function latestAlerts(state, limit = 3) {
  const runtimeAlerts = Array.isArray(state.alerts) ? state.alerts : [];
  const merged = [];
  const seen = new Set();
  for (const item of [...runtimeAlerts, ...meetingAlerts(state, 6)]) {
    const key = `${item.time || ""}|${item.summary || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }
  return merged.slice(0, limit);
}

function compactList(items) {
  return `
    <ul class="hq-summary-list">
      ${items
        .map(
          ([label, value]) => `
            <li>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(String(value))}</strong>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function marketLine(index) {
  if (!index) return "-- / -- / 休市";
  const session = index.session_status || "休市";
  const hasPrice = index.price != null && Number.isFinite(Number(index.price)) && Number(index.price) > 0;
  const hasChange = index.change_pct != null && Number.isFinite(Number(index.change_pct));
  const decimals = index.label === "黃金" ? 1 : 2;
  const priceText = hasPrice ? Number(index.price).toFixed(decimals) : "--";
  let direction = index.direction || "--";
  let changeText = "--";
  if (hasChange) {
    const changePct = Number(index.change_pct);
    direction = changePct > 0 ? "漲" : changePct < 0 ? "跌" : "平";
    changeText = `${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%`;
  } else if (!hasPrice) {
    direction = "--";
  }
  return `${priceText} / ${direction}${changeText} / ${session}`;
}

function renderCompactOverview(state) {
  const capital = state.capital || {};
  const pnl = state.pnl || {};
  const loans = state.loans || {};
  const internal = capital.internal_allocation || {};
  const binanceSpot = capital.binance_spot || {};
  const binanceFutures = capital.binance_futures || {};
  const totalLoans = Object.values(loans).reduce((sum, item) => sum + Number(item?.principal || 0), 0);
  return `
    <section class="hq-side-card">
      <header>
        <span>NEXUS HQ</span>
        <strong>狀態摘要</strong>
      </header>
      ${compactList([
        ["總資產", money(capital.total)],
        ["現貨 USDT", money(binanceSpot.usdt_total ?? capital.spot_usdt_total)],
        ["現貨 USDC", money(binanceSpot.usdc_total ?? capital.spot_usdc_total)],
        ["合約權益", money(binanceFutures.margin_balance ?? capital.futures_total)],
        ["合約錢包", money(binanceFutures.wallet_balance ?? capital.futures_wallet_display)],
        ["未實現", money(pnl.exchange_unrealized_pnl ?? pnl.total_pnl)],
        ["內部準備金", money(internal.hq_reserve ?? 0)],
        ["借款總額", money(totalLoans)],
      ])}
    </section>
  `;
}

function renderClockAndMarket(state) {
  const overview = state.market_overview || {};
  const times = overview.times || {};
  const indices = overview.indices || {};
  const decision = state.decision_summary || {};
  const transport = state.transport || {};

  return `
    <section class="hq-side-card hq-side-card--split">
      <div class="hq-side-split">
        <div class="hq-mini-panel">
          <header>
            <span>總站時鐘</span>
            <strong>時間與連線</strong>
          </header>
          ${compactList([
            ["台北時間", times.taipei || state.system?.current_time || "--"],
            ["美東時間", times.eastern || "--"],
            ["資料連線", transport.connected ? "在線" : "離線"],
            ["成交筆數", String(Number(decision.trade_count || 0))],
          ])}
        </div>
        <div class="hq-mini-panel">
          <header>
            <span>市場快照</span>
            <strong>外部市場</strong>
          </header>
          ${compactList([
            ["台股加權", marketLine(indices.twii)],
            ["標普 500", marketLine(indices.spx)],
            ["道瓊工業", marketLine(indices.dji)],
            ["那斯達克", marketLine(indices.nasdaq)],
            ["黃金", marketLine(indices.gold)],
          ])}
        </div>
      </div>
    </section>
  `;
}

function renderAlertCards(state) {
  const rows = latestAlerts(state, 3);
  if (!rows.length) {
    return `<div class="hq-side-empty">目前沒有新的警報。</div>`;
  }
  return rows
    .map(
      (item) => `
        <article class="hq-alert-card">
          <b>${escapeHtml(item.time || "--")}</b>
          <p>${escapeHtml(normalizeText(item.summary, "目前沒有可顯示的警報摘要。"))}</p>
        </article>
      `,
    )
    .join("");
}

function renderDecisionCard(state) {
  const meeting = latestMeeting(state);
  const conclusion = meeting?.conclusion || {};
  const summary = normalizeText(conclusion.summary || meeting?.summary, "目前沒有核心決策摘要。");
  const focus = (Array.isArray(conclusion.next_6h_focus) ? conclusion.next_6h_focus : []).slice(0, 3);
  return `
    <div class="hq-decision-card">
      <p>${escapeHtml(summary)}</p>
      <ul class="hq-decision-list">
        ${(focus.length ? focus : ["目前沒有新的焦點項目。"])
          .map((item) => `<li>${escapeHtml(normalizeText(item, "目前沒有新的焦點項目。"))}</li>`)
          .join("")}
      </ul>
    </div>
  `;
}

function renderRightSidebar(state) {
  return `
    <aside class="hq-side-stack">
      ${renderCompactOverview(state)}
      ${renderClockAndMarket(state)}
      <section class="hq-side-card">
        <header>
          <span>最新警報</span>
          <strong>會議警示</strong>
        </header>
        <div class="hq-alert-list">${renderAlertCards(state)}</div>
      </section>
      <section class="hq-side-card">
        <header>
          <span>核心決策</span>
          <strong>總部結論</strong>
        </header>
        ${renderDecisionCard(state)}
      </section>
    </aside>
  `;
}

function renderCenterStage() {
  return `
    <section class="hq-roundtable-stage">
      <img class="hq-roundtable-art" src="/static/nexus/assets/hq_roundtable.png" alt="HQ Roundtable Chamber" />
    </section>
  `;
}

function renderStationHtml(state) {
  const hotspots = getLayoutHotspots("HQ", HQ_HOTSPOTS);
  const hotspotHtml = hotspots
    .map(
      (h) => `
        <button
          class="station-hotspot-btn"
          data-hotspot-id="${h.id}"
          data-sub-modal="${h.section}"
          data-sub-label="${h.label}"
          data-page="HQ"
          style="left:${h.x * 100}%;top:${h.y * 100}%;width:${h.w * 100}%;height:${h.h * 100}%;"
          type="button"
        ><span>${h.label}</span></button>
      `,
    )
    .join("");

  return `
    <div class="station-page station-page--hq">
      <div class="station-main-area">
        <img class="station-main-img" src="/static/nexus/assets/hq_roundtable.png" alt="HQ Roundtable Chamber" />
        <div class="station-hotspot-layer">${hotspotHtml}</div>
      </div>
      <aside class="station-right-sidebar station-right-sidebar--hq">
        ${renderRightSidebar(state)}
      </aside>
    </div>
  `;
}

export function getHqModalContent(state, activeModal) {
  if (activeModal === "risk") {
    return `<div class="hq-alert-list">${renderAlertCards(state)}</div>`;
  }
  if (activeModal === "reports") {
    return renderDecisionCard(state);
  }
  return renderRightSidebar(state);
}

export function buildHqPage(state) {
  return {
    title: "HQ 圓桌會議",
    description: "總部圓桌會議畫面，整合市場、會議與警報摘要。",
    center: renderCenterStage(),
    right: renderRightSidebar(state),
    stationHtml: renderStationHtml(state),
  };
}
