import {
  FLEET_LABELS,
  getFleetData,
  renderConversation,
  renderPositions,
  renderRejects,
  renderStationOverviewCards,
  renderTrades,
} from "./scene_helpers.js?v=20260510a";
import { escapeHtml, normalizeText, translateSignal, translateStatus } from "../utils/presentation.js?v=20260510a";
import { getLayoutHotspots } from "../layout_state.js?v=20260503a";

const FLEET_ASSET = {
  BTC: "/static/nexus/assets/btc_bridge.png",
  ETH: "/static/nexus/assets/eth_bridge.png",
  SOL: "/static/nexus/assets/sol_bridge.png",
  PEPE: "/static/nexus/assets/pepe_bridge.png",
};

const FLEET_HOTSPOTS = [
  { id: "captain", label: "艦隊長", x: 0.38, y: 0.35, w: 0.22, h: 0.28, section: "discussion" },
  { id: "tactical", label: "訊號區", x: 0.62, y: 0.12, w: 0.34, h: 0.22, section: "signals" },
  { id: "analyst", label: "風險區", x: 0.16, y: 0.52, w: 0.18, h: 0.26, section: "risk" },
  { id: "quant", label: "訂單區", x: 0.76, y: 0.58, w: 0.2, h: 0.26, section: "orders" },
  { id: "news_desk", label: "報告區", x: 0.28, y: 0.68, w: 0.22, h: 0.24, section: "reports" },
  { id: "risk_panel", label: "持倉區", x: 0.62, y: 0.68, w: 0.18, h: 0.24, section: "overview" },
];

function renderPositionSummary(position, fleet) {
  if (!position) {
    return `<p class="panel-empty">目前沒有即時持倉。</p>`;
  }
  return `
    <div class="station-stat-row"><dt>方向</dt><dd>${escapeHtml(translateSignal(position.side || "HOLD"))}</dd></div>
    <div class="station-stat-row"><dt>槓桿</dt><dd>${Number(position.leverage || 1).toFixed(1)}x</dd></div>
    <div class="station-stat-row"><dt>數量</dt><dd>${Number(position.quantity || 0).toFixed(fleet === "PEPE" ? 2 : 4)}</dd></div>
    <div class="station-stat-row"><dt>開倉價</dt><dd>${Number(position.entry_price || 0).toFixed(fleet === "PEPE" ? 8 : 2)}</dd></div>
    <div class="station-stat-row"><dt>標記價</dt><dd>${Number(position.mark_price || 0).toFixed(fleet === "PEPE" ? 8 : 2)}</dd></div>
    <div class="station-stat-row"><dt>保證金</dt><dd>${Number(position.margin || 0).toFixed(2)}U</dd></div>
    <div class="station-stat-row"><dt>未實現損益</dt><dd>${Number(position.unrealized_pnl || 0).toFixed(2)}U</dd></div>
  `;
}

function renderStationHtml(fleet, state) {
  const hotspots = getLayoutHotspots(fleet, FLEET_HOTSPOTS);
  const hotspotHtml = hotspots.map((h) => `
    <button
      class="station-hotspot-btn"
      data-hotspot-id="${h.id}"
      data-sub-modal="${h.section}"
      data-sub-label="${h.label}"
      data-page="${fleet}"
      style="left:${h.x * 100}%;top:${h.y * 100}%;width:${h.w * 100}%;height:${h.h * 100}%;"
      type="button"
    ><span>${h.label}</span></button>
  `).join("");

  return `
    <div class="station-page">
      <div class="station-main-area">
        <img
          class="station-main-img"
          src="${FLEET_ASSET[fleet] || "/static/nexus/assets/hq_roundtable.png"}"
          alt="${escapeHtml(FLEET_LABELS[fleet] || fleet)} 操作中心"
        />
        <div class="station-hotspot-layer">${hotspotHtml}</div>
      </div>
      <aside class="station-right-sidebar">
        ${buildRightSidebar(fleet, state)}
      </aside>
    </div>
  `;
}

function buildRightSidebar(fleet, state) {
  const fd = getFleetData(state, fleet);
  const sys = fd.system || {};
  const cap = fd.capital || {};
  const pnl = fd.pnl || {};
  const livePosition = (fd.positions || [])[0];
  const latestTrade = (fd.trades || [])[0];

  const tradeHtml = latestTrade
    ? `
      <div style="font-size:12px;line-height:1.65;color:rgba(238,250,255,0.82);">
        <div>${escapeHtml(String(latestTrade.symbol || "--"))}</div>
        <div>${escapeHtml(translateSignal(latestTrade.side || "--"))} / ${Number(latestTrade.quantity ?? latestTrade.qty ?? 0).toFixed(4)}</div>
        <div>價格 ${Number(latestTrade.price || 0).toFixed(4)}</div>
        <div>${escapeHtml(latestTrade.timestamp || latestTrade.time || "--")}</div>
      </div>
    `
    : `<p style="color:rgba(255,255,255,0.42);font-size:12px;">目前沒有新的成交。</p>`;

  return `
    <p class="station-sidebar-title">${escapeHtml(FLEET_LABELS[fleet] || fleet)} 即時摘要</p>
    <div class="station-stat-row"><dt>艦隊狀態</dt><dd>${escapeHtml(translateStatus(sys.status || "NORMAL"))}</dd></div>
    <div class="station-stat-row"><dt>最新訊號</dt><dd>${escapeHtml(translateSignal(sys.last_signal || "HOLD"))}</dd></div>
    <div class="station-stat-row"><dt>可用資金</dt><dd>${Number(cap.available || 0).toFixed(2)}U</dd></div>
    <div class="station-stat-row"><dt>已實現</dt><dd>${Number(pnl.realized || 0).toFixed(2)}U</dd></div>
    <div class="station-stat-row"><dt>未實現</dt><dd>${Number((livePosition?.unrealized_pnl ?? pnl.unrealized) || 0).toFixed(2)}U</dd></div>
    <p class="station-sidebar-title" style="margin-top:10px;">即時持倉</p>
    ${renderPositionSummary(livePosition, fleet)}
    <p class="station-sidebar-title" style="margin-top:10px;">最新成交</p>
    ${tradeHtml}
  `;
}

export function getFleetModalContent(state, fleet, section) {
  const fd = getFleetData(state, fleet);
  const livePositions = fd.positions || [];

  if (section === "overview") {
    return renderPositions(livePositions, fleet);
  }
  if (section === "orders") {
    return renderTrades(fd.trades);
  }
  if (section === "signals") {
    const sys = fd.system || {};
    return `
      <div style="display:grid;gap:12px;">
        <div class="station-stat-row"><dt>最新訊號</dt><dd>${escapeHtml(translateSignal(sys.last_signal || "HOLD"))}</dd></div>
        <div class="station-stat-row"><dt>艦隊狀態</dt><dd>${escapeHtml(translateStatus(sys.status || "NORMAL"))}</dd></div>
        <p style="font-size:12px;color:rgba(238,250,255,0.74);margin:0;">${escapeHtml(normalizeText(sys.last_reason, "目前沒有新的訊號說明。"))}</p>
      </div>
    `;
  }
  if (section === "risk") {
    return renderRejects(fd.audits);
  }
  if (section === "discussion") {
    return renderConversation(state, fleet, 12);
  }
  if (section === "reports") {
    return renderStationOverviewCards(state, fleet);
  }
  return `<p style="color:rgba(255,255,255,0.42);">目前沒有可顯示的內容。</p>`;
}

export function buildFleetPage(fleet, state) {
  return {
    title: `${escapeHtml(FLEET_LABELS[fleet] || fleet)}`,
    description: `${escapeHtml(FLEET_LABELS[fleet] || fleet)} 的即時持倉、訊號、訂單與討論摘要。`,
    stationHtml: renderStationHtml(fleet, state),
  };
}
