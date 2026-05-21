import { renderConversation, renderStationOverviewCards } from "./scene_helpers.js?v=20260521f";
import { escapeHtml, normalizeText } from "../utils/presentation.js?v=20260510a";
import { getLayoutHotspots } from "../layout_state.js?v=20260503a";

const RADAR_HOTSPOTS = [
  { id: "whale", label: "巨鯨監控", x: 0.1, y: 0.3, w: 0.22, h: 0.3, section: "whale" },
  { id: "global", label: "全域警報", x: 0.5, y: 0.35, w: 0.24, h: 0.28, section: "alerts" },
  { id: "funding", label: "資金費率", x: 0.75, y: 0.55, w: 0.2, h: 0.28, section: "funding" },
  { id: "monitor", label: "站內通訊", x: 0.28, y: 0.65, w: 0.18, h: 0.24, section: "reports" },
];

function renderStationHtml(state) {
  const hotspots = getLayoutHotspots("RADAR", RADAR_HOTSPOTS);
  const hotspotHtml = hotspots
    .map(
      (h) => `
        <button
          class="station-hotspot-btn"
          data-hotspot-id="${h.id}"
          data-sub-modal="${h.section}"
          data-sub-label="${h.label}"
          data-page="RADAR"
          style="left:${h.x * 100}%;top:${h.y * 100}%;width:${h.w * 100}%;height:${h.h * 100}%;"
          type="button"
        ><span>${h.label}</span></button>
      `,
    )
    .join("");

  return `
    <div class="station-page">
      <div class="station-main-area">
        <img class="station-main-img" src="/static/nexus/assets/radar_outpost.png" alt="雷達站" />
        <div class="station-hotspot-layer">${hotspotHtml}</div>
      </div>
      <aside class="station-right-sidebar">
        ${buildRightSidebar(state)}
      </aside>
    </div>
  `;
}

function buildRightSidebar(state) {
  const alerts = (state.alerts || []).slice(0, 4);
  const alertsHtml = alerts.length
    ? alerts
        .map(
          (a) => `<div class="station-alert-row"><b>${escapeHtml(a.time || "--")}</b>${escapeHtml(normalizeText(a.summary || "警報"))}</div>`,
        )
        .join("")
    : `<p style="color:rgba(255,255,255,0.4);font-size:12px;">目前沒有新的雷達警報。</p>`;

  return `
    <p class="station-sidebar-title">RADAR 雷達站</p>
    <div class="station-stat-row"><dt>站點狀態</dt><dd>在線監控</dd></div>
    <p class="station-sidebar-title" style="margin-top:8px;">最新警報</p>
    ${alertsHtml}
  `;
}

export function getRadarModalContent(state, section) {
  if (section === "whale") {
    return renderStationOverviewCards(state, "WHALE") || `<p style="color:rgba(255,255,255,0.4);">目前沒有巨鯨監控資料。</p>`;
  }
  if (section === "alerts") {
    const alerts = (state.alerts || []).slice(0, 15);
    if (!alerts.length) return `<p style="color:rgba(255,255,255,0.4);">目前沒有新的雷達警報。</p>`;
    return alerts
      .map(
        (a) => `<div class="station-alert-row"><b>${escapeHtml(a.time || "--")}</b>${escapeHtml(normalizeText(a.summary || "警報"))}</div>`,
      )
      .join("");
  }
  if (section === "funding") {
    return renderStationOverviewCards(state, "FUNDING") || `<p style="color:rgba(255,255,255,0.4);">目前沒有資金費率摘要。</p>`;
  }
  if (section === "reports") {
    return renderConversation(state, "RADAR", 10) || `<p style="color:rgba(255,255,255,0.4);">目前沒有站內通訊紀錄。</p>`;
  }
  return `<p style="color:rgba(255,255,255,0.4);">目前沒有可顯示的雷達內容。</p>`;
}

export function buildRadarPage(state) {
  return {
    title: "雷達站",
    description: "集中監看巨鯨、警報、資金費率與雷達通訊。",
    stationHtml: renderStationHtml(state),
  };
}
