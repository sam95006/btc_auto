import {
  buildRejectNarration,
  buildRoleWindows,
  buildStationConversation,
  escapeHtml,
  formatUnit,
  getLatestMeeting,
  normalizeText,
  translateMeetingType,
  translateSignal,
  translateStation,
  translateStatus,
  translateTradeEvent,
} from "../utils/presentation.js?v=20260510a";

export const PAGE_META = {
  MAIN: { title: "總站總覽", description: "集中顯示母港、各艦隊節點、情報站與圓桌會議摘要。" },
  HQ: { title: "HQ 圓桌會議", description: "總部決策中心，整合警報、會議與市場摘要。" },
  BTC: { title: "BTC 艦隊", description: "BTC 艦隊的即時持倉、訊號、拒單與討論。" },
  ETH: { title: "ETH 艦隊", description: "ETH 艦隊的即時持倉、訊號、拒單與討論。" },
  SOL: { title: "SOL 艦隊", description: "SOL 艦隊的即時持倉、訊號、拒單與討論。" },
  PEPE: { title: "PEPE 艦隊", description: "PEPE 艦隊的即時持倉、訊號、拒單與討論。" },
  RADAR: { title: "雷達站", description: "巨鯨、資金費率、異常波動與市場掃描。" },
  NEWS: { title: "新聞站", description: "宏觀數據、聯準會與加密新聞分類整理。" },
};

export const FLEET_LABELS = {
  BTC: "BTC 艦隊",
  ETH: "ETH 艦隊",
  SOL: "SOL 艦隊",
  PEPE: "PEPE 艦隊",
};

export function card(title, body, subtitle = "") {
  return `
    <section class="workspace-card">
      <header class="workspace-card-header">
        <div>
          <h3>${escapeHtml(title)}</h3>
          ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
        </div>
      </header>
      <div class="workspace-card-body">${body}</div>
    </section>
  `;
}

function listMarkup(items, emptyText = "目前沒有資料。") {
  if (!Array.isArray(items) || !items.length) {
    return `<p class="panel-empty">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="panel-list">${items.map((item) => `<li>${escapeHtml(normalizeText(item, emptyText))}</li>`).join("")}</ul>`;
}

export function getFleetData(state, fleet) {
  const liveMode = Array.isArray(state.positions) && state.positions.some((item) => String(item.id || "").startsWith("live_"));
  const embedded = state.fleet_data?.[fleet];
  if (embedded) {
    const positions = embedded.positions || [];
    const livePosition = positions[0];
    const system = { ...(embedded.system || {}) };
    let trades = embedded.trades || [];
    if (livePosition) {
      system.status = "TRADING";
      system.last_signal = livePosition.side || system.last_signal || "HOLD";
      system.last_reason = "binance_live_position";
      trades = [{
        event: "LIVE",
        fleet,
        symbol: livePosition.symbol,
        side: livePosition.side,
        quantity: livePosition.quantity,
        price: livePosition.entry_price,
        leverage: livePosition.leverage,
        margin: livePosition.margin,
        pnl: livePosition.unrealized_pnl,
        time: livePosition.opened_at,
      }];
    } else if (liveMode) {
      system.status = "MONITORING";
      system.last_signal = "HOLD";
      system.last_reason = "no_live_position";
      trades = [];
    }
    return {
      system,
      capital: embedded.capital || {},
      pnl: embedded.pnl || {},
      positions,
      trades,
      audits: (state.decision_audit || []).filter((item) => String(item.symbol || "").toUpperCase().includes(fleet)),
      briefing: embedded.briefing || state.station_briefings?.[fleet] || {},
    };
  }

  const positions = (state.positions || []).filter((item) => item.fleet === fleet);
  const livePosition = positions[0];
  const system = { ...(state.system?.fleet_status?.[fleet] || {}) };
  let trades = (state.trades || []).filter((item) => item.fleet === fleet);
  if (livePosition) {
    system.status = "TRADING";
    system.last_signal = livePosition.side || system.last_signal || "HOLD";
    system.last_reason = "binance_live_position";
    trades = [{
      event: "LIVE",
      fleet,
      symbol: livePosition.symbol,
      side: livePosition.side,
      quantity: livePosition.quantity,
      price: livePosition.entry_price,
      leverage: livePosition.leverage,
      margin: livePosition.margin,
      pnl: livePosition.unrealized_pnl,
      time: livePosition.opened_at,
    }];
  } else if (liveMode) {
    system.status = "MONITORING";
    system.last_signal = "HOLD";
    system.last_reason = "no_live_position";
    trades = [];
  }

  return {
    system,
    capital: state.capital?.fleets?.[fleet] || {},
    pnl: state.pnl?.fleets?.[fleet] || {},
    positions,
    trades,
    audits: (state.decision_audit || []).filter((item) => String(item.symbol || "").toUpperCase().includes(fleet)),
    briefing: state.station_briefings?.[fleet] || {},
  };
}

export function renderPositions(positions, fleet) {
  if (!positions.length) {
    return `<p class="panel-empty">目前沒有即時持倉。</p>`;
  }

  return positions.map((position) => `
    <article class="data-line">
      <b>${escapeHtml(translateSignal(position.side || ""))} / ${escapeHtml(String(position.symbol || "--"))}</b>
      <div>
        槓桿 ${Number(position.leverage || 1).toFixed(1)}x<br>
        數量 ${Number(position.quantity || 0).toFixed(fleet === "PEPE" ? 2 : 4)}<br>
        開倉價 ${Number(position.entry_price || 0).toFixed(fleet === "PEPE" ? 8 : 2)}<br>
        標記價 ${Number(position.mark_price || 0).toFixed(fleet === "PEPE" ? 8 : 2)}<br>
        保證金 ${Number(position.margin || 0).toFixed(2)}U<br>
        未實現損益 ${Number(position.unrealized_pnl || 0).toFixed(2)}U
      </div>
    </article>
  `).join("");
}

export function renderTrades(trades, limit = 12) {
  if (!trades.length) {
    return `<p class="panel-empty">目前沒有新的成交紀錄。</p>`;
  }

  return trades.slice(0, limit).map((trade) => {
    const qty = Number(trade.quantity ?? trade.qty ?? 0);
    return `
      <article class="data-line">
        <b>${escapeHtml(translateTradeEvent(trade.event || "TRADE"))} ${escapeHtml(translateSignal(trade.side || ""))}</b>
        <div>
          價格 ${Number(trade.price || 0).toFixed(4)}<br>
          數量 ${qty.toFixed(4)}<br>
          損益 ${Number(trade.pnl || 0).toFixed(2)}U<br>
          時間 ${escapeHtml(trade.timestamp || trade.time || "--")}
        </div>
      </article>
    `;
  }).join("");
}

export function renderRejects(audits, limit = 10) {
  if (!audits.length) {
    return `<p class="panel-empty">目前沒有拒單紀錄。</p>`;
  }

  return audits.slice(0, limit).map((item) => `
    <article class="data-line">
      <b>${escapeHtml(item.symbol || "--")}</b>
      <div>${escapeHtml(buildRejectNarration(item.reject_layer, item.reject_reason))}</div>
    </article>
  `).join("");
}

export function renderConversation(state, station, limit = 14) {
  const rows = buildStationConversation(state, station).slice(-limit);
  if (!rows.length) {
    return `<p class="panel-empty">目前沒有站內通訊內容。</p>`;
  }

  return rows.map((row) => `
    <article class="chat-line chat-${String(row.importance || "info").toLowerCase()}">
      <header>
        <b>${escapeHtml(row.speaker || "系統")}</b>
        <span>${escapeHtml(row.timestamp || "--")} / ${escapeHtml(row.source || "站內通訊")}</span>
      </header>
      <p>${escapeHtml(normalizeText(row.message, "目前沒有新的通訊內容。"))}</p>
    </article>
  `).join("");
}

export function renderRoleSpotlight(state, station, index = 0) {
  const roles = buildRoleWindows(state, station);
  if (!roles.length) {
    return `<p class="panel-empty">目前沒有角色資訊。</p>`;
  }
  const active = roles[Math.max(0, Math.min(index, roles.length - 1))];
  return `
    <article class="role-spotlight">
      <header><h4>${escapeHtml(active.role)}</h4></header>
      <div class="role-meta">
        <strong>目前任務</strong>
        <p>${escapeHtml(normalizeText(active.currentTask, "目前沒有新的任務。"))}</p>
      </div>
      <div class="role-meta">
        <strong>最新回報</strong>
        <p>${escapeHtml(normalizeText(active.latestSpeech, "目前沒有新的回報。"))}</p>
      </div>
      <div class="role-meta">
        <strong>討論重點</strong>
        ${listMarkup(active.discussion, "目前沒有新的討論重點。")}
      </div>
    </article>
  `;
}

export function renderRoleMatrix(state, station) {
  const roles = buildRoleWindows(state, station);
  if (!roles.length) {
    return `<p class="panel-empty">目前沒有角色資訊。</p>`;
  }
  return `
    <div class="role-matrix">
      ${roles.map((role, index) => `
        <button type="button" class="role-mini-card" data-role-index="${index}">
          <h4>${escapeHtml(role.role)}</h4>
          <p>${escapeHtml(normalizeText(role.currentTask, "目前沒有新的任務。"))}</p>
          <small>${escapeHtml(normalizeText(role.latestSpeech, "目前沒有新的回報。"))}</small>
        </button>
      `).join("")}
    </div>
  `;
}

export function renderMeetingSummary(state, slot = null) {
  const meetings = Array.isArray(state.meetings) ? state.meetings : [];
  const meeting = slot
    ? meetings.find((item) => String(item.time || "").slice(11, 16) === slot) || null
    : getLatestMeeting(state);

  if (!meeting) {
    return `<p class="panel-empty">目前沒有會議結果。</p>`;
  }

  const conclusion = meeting.conclusion || {};
  const focus = (Array.isArray(conclusion.next_6h_focus) ? conclusion.next_6h_focus : []).slice(0, 3);
  return `
    <article class="meeting-summary-card">
      <header>
        <b>${escapeHtml(translateMeetingType(meeting.type || "SCHEDULED_ROUND_TABLE"))}</b>
        <span>${escapeHtml(meeting.time || "--")}</span>
      </header>
      <p>${escapeHtml(normalizeText(conclusion.summary || meeting.summary, "目前沒有可顯示的會議摘要。"))}</p>
      ${listMarkup(focus, "目前沒有新的焦點項目。")}
    </article>
  `;
}

export function renderQuickStats(state, station) {
  if (station === "HQ") {
    const capital = state.capital || {};
    const pnl = state.pnl || {};
    const internal = capital.internal_allocation || {};
    const spot = capital.binance_spot || {};
    const futures = capital.binance_futures || {};
    const unrealized = pnl.exchange_unrealized_pnl ?? pnl.total_pnl ?? 0;
    return `
      <div class="quick-stats-grid">
        <div><span>總資產</span><strong>${formatUnit(capital.total)}</strong></div>
        <div><span>現貨 USDT/USDC</span><strong>${formatUnit(spot.stable_total ?? capital.spot_stable_total)}</strong></div>
        <div><span>合約權益</span><strong>${formatUnit(futures.margin_balance ?? capital.futures_total)}</strong></div>
        <div><span>未實現</span><strong>${formatUnit(unrealized)}</strong></div>
        <div><span>內部準備金</span><strong>${formatUnit(internal.hq_reserve ?? 0)}</strong></div>
      </div>
    `;
  }

  const fleet = getFleetData(state, station);
  return `
    <div class="quick-stats-grid">
      <div><span>可用資金</span><strong>${formatUnit(fleet.capital?.available)}</strong></div>
      <div><span>已實現</span><strong>${formatUnit(fleet.pnl?.realized)}</strong></div>
      <div><span>狀態</span><strong>${escapeHtml(translateStatus(fleet.system?.status || "NORMAL"))}</strong></div>
    </div>
  `;
}

export function renderStationOverviewCards(state, station) {
  const briefing = state.station_briefings?.[station] || {};
  const blocks = [
    normalizeText(briefing.summary, "目前沒有站點摘要。"),
    normalizeText((briefing.watchlist || []).join(" / "), "目前沒有監控名單。"),
    normalizeText((briefing.risk_notes || []).join(" / "), "目前沒有新的風險備註。"),
  ];
  return `<div class="overview-card-stack">${blocks.map((text) => `<article class="overview-card">${escapeHtml(text)}</article>`).join("")}</div>`;
}

export function renderStationFeedSummary(state, station) {
  const rows = buildStationConversation(state, station).slice(-4);
  return rows.length
    ? `<ul class="panel-list">${rows.map((row) => `<li>${escapeHtml(normalizeText(row.message, "目前沒有新的通訊內容。"))}</li>`).join("")}</ul>`
    : `<p class="panel-empty">目前沒有新的站點摘要。</p>`;
}

export function buildPageMeta(pageId) {
  return PAGE_META[pageId] || { title: pageId, description: "目前沒有頁面描述。" };
}

export function fleetSections() {
  return ["overview", "orders", "signals", "risk", "discussion", "reports"];
}

export function hqSections() {
  return ["overview", "decisions", "risk", "discussion", "reports", "restrictions"];
}
