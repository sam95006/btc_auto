import { escapeHtml } from "../utils/presentation.js?v=20260525a";

function sourceLabel(item) {
  return (
    item.decision_source ||
    item.proposer ||
    item.source ||
    "system"
  );
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
        <span>${fleet} ${symbol}</span>
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
    ? `漏斗 提案${stages.proposals}→核准${stages.audit_approved || 0}→成交${stages.executed_futures_closes || 0}`
    : "漏斗待樣本";
  const rejectNote = topRejects.length
    ? ` · 拒絕 ${escapeHtml(topRejects.map((r) => r.reason).join(", "))}`
    : "";
  const system = state.system || {};
  const paused = Boolean(system.trading_paused);
  const pauseReason = String(system.pause_reason || "").trim();
  const blockReason = String(system.block_reason || "").trim();
  let diagnosisText = "";
  if (paused) {
    diagnosisText = pauseReason
      ? `交易暫停：${pauseReason}`
      : "交易暫停中（請在聊天輸入「恢復交易」或檢查 Zeabur env）";
  } else if (system.block_new_entries && blockReason) {
    diagnosisText = `運行中但擋新倉：${blockReason}`;
  } else if (funnel.diagnosis) {
    diagnosisText = String(funnel.diagnosis);
  }
  const diagnosis = diagnosisText
    ? `<p class="decision-diagnosis">${escapeHtml(compact ? diagnosisText.slice(0, 140) : diagnosisText)}</p>`
    : "";

  let host = root.querySelector(".decision-strip-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "decision-strip-host";
    root.appendChild(host);
  }
  host.dataset.scrollKey = "decision-strip";
  host.innerHTML = `
    <div class="decision-strip">
      <header>
        <strong>決策稽核</strong>
        <small>${traceNote} · 演化 ${evoMode} · ${funnelNote}${rejectNote} · 管倉 ${posActions}</small>
      </header>
      ${diagnosis}
      <ul class="decision-list">${rows || "<li class='decision-row'>尚無決策樣本</li>"}</ul>
      ${compact && audits.length > 2 ? `<button type="button" class="decision-more-btn" data-decision-expand>展開更多</button>` : ""}
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
