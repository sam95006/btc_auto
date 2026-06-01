import { escapeHtml } from "../utils/presentation.js?v=20260601a";

function fmtTime(ts) {
  const n = Number(ts || 0);
  if (!n) return "—";
  try {
    const d = new Date(n);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}

function checkRow(item) {
  const ok = Boolean(item.ok);
  return `<li class="pure-ai-check ${ok ? "ok" : "bad"}">
    <span>${ok ? "✓" : "✗"} ${escapeHtml(item.label || item.id || "check")}</span>
    <small>${escapeHtml(item.detail || "")}</small>
  </li>`;
}

function proposalRow(item) {
  if (!item || typeof item !== "object") return "";
  return `<li class="pure-ai-proposal">
    <strong>${escapeHtml(item.symbol || "—")}</strong>
    <span>${escapeHtml(item.side || "—")} · ${escapeHtml(String(item.leverage ?? "—"))}x · margin ${escapeHtml(String(item.margin ?? "—"))}</span>
    <small>${escapeHtml(item.decision_source || item.proposer || "pure_ai_trader")}</small>
  </li>`;
}

export function renderPureAiPanel(root, state) {
  if (!root) return;
  const status = state.pure_ai_status || {};
  const active = Boolean(state.pure_ai_enabled ?? status.active);
  const operational = Boolean(status.operational);
  const checks = Array.isArray(status.verification_checks) ? status.verification_checks : [];
  const cycle = status.last_cycle || state.pure_ai_trader || {};
  const pipeline = status.pipeline || state.entry_pipeline || {};
  const llm = status.llm || {};
  const proposals = list(cycle.entry_proposals || [], 4);
  const exits = list(cycle.exit_actions || [], 4);

  let host = root.querySelector(".pure-ai-panel-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "pure-ai-panel-host";
    root.appendChild(host);
  }

  host.innerHTML = `
    <div class="pure-ai-panel">
      <header class="pure-ai-head">
        <span class="pure-ai-badge ${operational ? "is-live" : active ? "is-on" : "is-off"}">
          ${operational ? "PURE AI 運行中" : active ? "PURE AI 已啟用" : "非 Pure AI 模式"}
        </span>
        <h3>${escapeHtml(status.headline || (active ? "Pure AI 全自動" : "混合模式"))}</h3>
        <p class="pure-ai-explainer">${escapeHtml(status.explanation || "")}</p>
      </header>

      <section class="pure-ai-metrics">
        <div><span>管線</span><strong>${escapeHtml(String(pipeline.mode || "—"))}</strong></div>
        <div><span>本輪提案</span><strong>${Number(cycle.entry_count ?? pipeline.candidates ?? 0)}</strong></div>
        <div><span>本輪成交</span><strong>${Number(pipeline.executed ?? 0)}</strong></div>
        <div><span>可部署資金</span><strong>${Number(cycle.deployable_pool ?? pipeline.deployable_pool ?? 0).toFixed(0)}U</strong></div>
        <div><span>LLM</span><strong>${llm.enabled ? escapeHtml(llm.flex_trade_model || "online") : "offline"}</strong></div>
        <div><span>更新</span><strong>${fmtTime(cycle.timestamp)}</strong></div>
      </section>

      <section class="pure-ai-section">
        <h4>驗證清單（如何確認是 AI 在決策）</h4>
        <ul class="pure-ai-checks">${checks.map(checkRow).join("") || "<li>載入中…</li>"}</ul>
      </section>

      <section class="pure-ai-section">
        <h4>最新進場提案（LLM → pure_ai_trader）</h4>
        <ul class="pure-ai-proposals">${proposals.map(proposalRow).join("") || "<li class='pure-ai-empty'>本輪 LLM 尚未提案（可能觀望或限流）</li>"}</ul>
      </section>

      <section class="pure-ai-section">
        <h4>最新出場動作（flex_exit_eval）</h4>
        <ul class="pure-ai-proposals">${exits.map((item) => `<li class="pure-ai-proposal"><strong>${escapeHtml(item.symbol || "—")}</strong><span>${escapeHtml(item.action || item.decision || "—")}</span></li>`).join("") || "<li class='pure-ai-empty'>目前無出場指令</li>"}</ul>
      </section>

      <footer class="pure-ai-foot">
        <small>${escapeHtml(status.pnl_disclaimer || "")}</small>
        <a href="/api/nexus/pure-ai-status" target="_blank" rel="noopener">API 驗證 JSON ↗</a>
      </footer>
    </div>
  `;
}

function list(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}
