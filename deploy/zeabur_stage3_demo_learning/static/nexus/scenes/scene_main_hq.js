import { escapeHtml, translateSignal, translateStatus } from "../utils/presentation.js?v=20260510a";
import { getLayoutHotspots } from "../layout_state.js?v=20260601a";

const MAP_NODES = [
  { id: "HQ", label: "Stage 3 Learning HQ", x: 0.5, y: 0.478, w: 0.13, h: 0.346 },
  { id: "BTC", label: "Market Scanner", x: 0.728, y: 0.304, w: 0.113, h: 0.162 },
  { id: "ETH", label: "Bybit Demo Executor", x: 0.743, y: 0.794, w: 0.15, h: 0.149 },
  { id: "SOL", label: "Balance / Risk Monitor", x: 0.271, y: 0.769, w: 0.133, h: 0.189 },
  { id: "PEPE", label: "Stage 3 Event Log", x: 0.277, y: 0.315, w: 0.152, h: 0.179 },
  { id: "RADAR", label: "Learning Evidence", x: 0.095, y: 0.539, w: 0.136, h: 0.229 },
  { id: "NEWS", label: "Safety Gates", x: 0.906, y: 0.515, w: 0.15, h: 0.209 },
];

function renderMap(state, stage3) {
  const nodes = getLayoutHotspots("MAIN", MAP_NODES);
  const runner = stage3?.runner || {};
  const phase = stage3?.runner_phase || "IDLE";
  return `
    <div class="scene-stage-frame home-stage-frame" style="position:relative;width:100%;max-width:1536px;margin:0 auto;overflow:visible;">
      <img class="scene-stage-art" src="/static/nexus/assets/nexus_overview.png" style="width:100%;height:auto;display:block;" alt="Nexus Overview" onerror="this.style.display='none';this.parentElement.querySelector('.missing-art')?.removeAttribute('hidden');" />
      <div class="missing-art" hidden>
        <b>主地圖載入中</b>
        <span>若長時間空白，請重新整理或等待部署完成</span>
      </div>
      <div class="scene-stage-hotspots" style="z-index:10;position:absolute;inset:0;">
        ${nodes.map((node) => {
          let signal = "Demo Learning";
          let status = phase;
          if (node.id === "ETH") {
            signal = `${Number(runner.orders_sent || 0)}/${Number(runner.max_orders_per_day || 6)} orders`;
            status = runner.latest_order_id ? "ORDER SENT" : "IDLE";
          } else if (node.id === "SOL") {
            signal = `open ${Number(runner.open_positions_current || 0)}`;
            status = "RISK MONITOR";
          } else if (node.id === "HQ") {
            signal = stage3?.startup_mode || "idle";
            status = phase;
          } else if (node.id === "RADAR") {
            signal = `trades ${Number(stage3?.learning?.trade_results_count || 0)}`;
            status = "EVIDENCE";
          } else if (node.id === "NEWS") {
            signal = "demo only";
            status = stage3?.safety?.bybit_mainnet_allowed ? "ALERT" : "SAFE";
          }
          return `
            <button
              type="button"
              class="scene-hotspot-block ${phase === "STOPPED" && node.id === "HQ" ? "is-alert" : ""}"
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

export function buildMainOverviewPage(state, homeUiState = {}, stage3 = null) {
  return {
    title: "Stage 3 Demo Learning",
    description: "Bybit Demo/Testnet 24h learning runner · read-only dashboard.",
    center: renderMap(state, stage3),
    right: "",
  };
}
