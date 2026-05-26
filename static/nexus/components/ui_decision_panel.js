import { escapeHtml } from "../utils/presentation.js?v=20260526e";

function sourceLabel(item) {
  return item.decision_source || item.proposer || item.source || "system";
}

function pauseReasonLabel(reason) {
  const key = String(reason || "").trim().toLowerCase();
  const map = {
    consecutive_losses: "連續虧損達風控上限（已改為警示，可恢復交易）",
    validation_choke: "驗證拒絕率過高",
    exchange_sync_stale: "交易所同步延遲",
    daily_max_loss: "日損上限",
    manual: "手動暫停",
    news: "新聞熔斷",
  };
  for (const [token, label] of Object.entries(map)) {
    if (key.includes(token)) return label;
  }
  return reason || "未知原因";
}

export function renderDecisionStrip(root, state, options = {}) {
  if (!root) return;
  const compact = Boolean(options.compact);
  const audits = list(state.decision_audit || [], compact ? 3 : 6);
  const traces = list(state.decision_traces || [], 3);
  const evolution = state.strategy_evolution || {};
  const positionAi = state.position_ai || {};
  const funnel = state.decision_funnel || {};
  const stages = funnel.stages || {};
  const topRejects = (funnel.top_reject_reasons || []).slice(0, 3);

  const rows = audits
    .map((item) => {
      const ok = Boolean(item.approved);
      const symbol = escapeHtml(item.symbol || "--");
      const fleet = escapeHtml(item.fleet || "--");
      const source = escapeHtml(String(sourceLabel(item)));
      const reason = escapeHtml(item.reject_reason || item.reason || (ok ? "approved" : "blocked"));
      return `<li class="decision-row ${ok ? "ok" : "block"}">
        <span>${fleet} · ${symbol}</span>
        <small>${source} · ${reason}</small>
      </li>`;
    })
    .join("");

  const traceNote =
    traces.length > 0
      ? `trace ${escapeHtml(traces[0].trace_id || traces[0].id || "latest")}`
      : "no traces yet";
  const evoMode = escapeHtml(evolution.evolution_mode || evolution.mode || "hold");
  const posActions = Number((positionAi.actions || []).length || 0);
  const funnelNote = stages.proposals
    ? `提案 ${stages.proposals} → 核准 ${stages.audit_approved || 0} → 成交 ${stages.executed_futures_closes || 0}`
    : "漏斗待樣本";

  const system = state.system || {};
  const paused = Boolean(system.trading_paused);
  const pauseReason = String(system.pause_reason || "").trim();
  const blockReason = String(system.block_reason || "").trim();

  let statusBanner = "";
  if (paused) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--pause">⏸ ${escapeHtml(
      pauseReasonLabel(pauseReason),
    )}</div>`;
  } else if (system.block_new_entries && blockReason) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--warn">⚠ 運行中但擋新倉：${escapeHtml(
      blockReason,
    )}</div>`;
  } else if (funnel.diagnosis && !paused) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--warn">${escapeHtml(
      compact ? String(funnel.diagnosis).slice(0, 120) : funnel.diagnosis,
    )}</div>`;
  }

  const chips = [
    `<span class="decision-chip">${funnelNote}</span>`,
    `<span class="decision-chip">演化 ${evoMode}</span>`,
    `<span class="decision-chip">管倉 ${posActions}</span>`,
  ];
  if (topRejects.length) {
    chips.push(
      `<span class="decision-chip">拒絕 ${escapeHtml(topRejects.map((r) => r.reason).join(", "))}</span>`,
    );
  }

  let host = root.querySelector(".decision-strip-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "decision-strip-host";
    root.appendChild(host);
  }
  host.dataset.scrollKey = "decision-strip";
  host.innerHTML = `
    <div class="decision-strip decision-strip--premium">
      <header>
        <strong>決策稽核</strong>
        <small>${traceNote}</small>
        <div class="decision-meta-chips">${chips.join("")}</div>
      </header>
      ${statusBanner}
      <ul class="decision-list">${rows || "<li class='decision-row'>尚無決策樣本</li>"}</ul>
      ${compact && audits.length > 2 ? `<button type="button" class="decision-more-btn" data-decision-expand>展開更多紀錄</button>` : ""}
    </div>
  `;
  if (compact) {
    host.querySelector("[data-decision-expand]")?.addEventListener("click", () => {
      renderDecisionStrip(root, state, { compact: false });
    });
  }
}

function list(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}
