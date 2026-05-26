import { escapeHtml } from "../utils/presentation.js?v=20260525a";

function sourceLabel(item) {
  return (
    item.decision_source ||
    item.proposer ||
    item.source ||
    "system"
  );
}

export function renderDecisionStrip(root, state) {
  if (!root) return;
  const audits = list(state.decision_audit || [], 6);
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
  const diagnosis = funnel.diagnosis ? `<p class="decision-diagnosis">${escapeHtml(funnel.diagnosis)}</p>` : "";

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
    </div>
  `;
}

function list(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}
