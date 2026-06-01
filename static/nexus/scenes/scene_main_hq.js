import { escapeHtml, translateSignal, translateStatus } from "../utils/presentation.js?v=20260510a";
import { getLayoutHotspots } from "../layout_state.js?v=20260601a";

const MAP_NODES = [
  { id: "HQ", label: "NEXUS 母港", x: 0.5, y: 0.478, w: 0.13, h: 0.346 },
  { id: "BTC", label: "BTC 艦隊", x: 0.728, y: 0.304, w: 0.113, h: 0.162 },
  { id: "ETH", label: "ETH 艦隊", x: 0.743, y: 0.794, w: 0.15, h: 0.149 },
  { id: "SOL", label: "SOL 艦隊", x: 0.271, y: 0.769, w: 0.133, h: 0.189 },
  { id: "PEPE", label: "PEPE 艦隊", x: 0.277, y: 0.315, w: 0.152, h: 0.179 },
  { id: "RADAR", label: "雷達站", x: 0.095, y: 0.539, w: 0.136, h: 0.229 },
  { id: "NEWS", label: "新聞站", x: 0.906, y: 0.515, w: 0.15, h: 0.209 },
];

function renderMap(state) {
  const nodes = getLayoutHotspots("MAIN", MAP_NODES);
  return `
    <div class="scene-stage-frame home-stage-frame" style="position:relative;width:100%;max-width:1536px;margin:0 auto;overflow:visible;">
      <img class="scene-stage-art" src="/static/nexus/assets/nexus_overview.png" style="width:100%;height:auto;display:block;" alt="Nexus Overview" onerror="this.style.display='none';this.parentElement.querySelector('.missing-art')?.removeAttribute('hidden');" />
      <div class="missing-art" hidden>
        <b>主地圖載入中</b>
        <span>若長時間空白，請重新整理或等待部署完成</span>
      </div>
      <div class="scene-stage-hotspots" style="z-index:10;position:absolute;inset:0;">
        ${nodes.map((node) => {
          const livePosition = (state.positions || []).find((item) => item.fleet === node.id && String(item.id || "").startsWith("live_"));
          const fleetStatus = state.system?.fleet_status?.[node.id];
          const positionSide = livePosition
            ? (Number(livePosition.signed_quantity ?? livePosition.quantity ?? 0) > 0 ? "LONG" : "SHORT")
            : (fleetStatus?.last_signal || "HOLD");
          const signal = translateSignal(positionSide);
          const status = translateStatus(
            livePosition
              ? "TRADING"
              : (fleetStatus?.status || (node.id === "HQ" ? state.system?.system_health : "NORMAL")),
          );
          const alert = state.system?.alert_level !== "NORMAL" && node.id === "HQ";
          return `
            <button
              type="button"
              class="scene-hotspot-block ${alert ? "is-alert" : ""}"
              data-layout-page="MAIN"
              data-hotspot-id="${node.id}"
              data-open-page="${node.id}"
              style="left:${node.x * 100}%;top:${node.y * 100}%;width:${node.w * 100}%;height:${node.h * 100}%;">
              <span style="font-size:14px;margin-bottom:4px;display:block;">${escapeHtml(node.label)}</span>
              <span style="font-size:11px;opacity:0.84;">${escapeHtml(signal)} / ${escapeHtml(status)}</span>
            </button>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

export function getMainModalContent() {
  return `<p class="panel-empty">請從主地圖熱區打開對應站點。</p>`;
}

export function buildMainOverviewPage(state) {
  return {
    title: "總站總覽",
    description: "集中顯示母港、艦隊與各站點熱區。",
    center: renderMap(state),
    right: "",
  };
}
