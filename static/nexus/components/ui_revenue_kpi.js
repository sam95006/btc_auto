import { escapeHtml } from "../utils/presentation.js?v=20260526a";

function money(value) {
  return `${Number(value || 0).toFixed(2)}U`;
}

export function renderRevenueKpi(root, state, options = {}) {
  if (!root) return;
  const compact = Boolean(options.compact);
  const monthly = state.monthly_revenue || {};
  const plan = state.revenue_plan || {};
  const target = Number(monthly.target_usd || 0);
  const net = Number(monthly.realized_pnl_net || 0);
  const progress = Number(monthly.progress_pct || 0);
  const remaining = Number(monthly.remaining_usd || 0);
  const equity = Number(monthly.current_futures_equity || plan.futures_equity_usd || 0);
  const reqPct = Number(monthly.required_monthly_return_pct || plan.required_monthly_return_pct || 0);
  const stage = Number(plan.current_stage || 0);
  const met = Boolean(monthly.target_met);
  const tone = met ? "good" : progress >= 50 ? "" : net < 0 ? "bad" : "";

  let host = root.querySelector(".revenue-kpi-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "revenue-kpi-host";
    root.appendChild(host);
  }
  host.dataset.scrollKey = "revenue-kpi";
  host.innerHTML = compact
    ? `
    <div class="revenue-kpi revenue-kpi--compact ${tone}">
      <header>
        <strong>月營收</strong>
        <small>${money(equity)} 池</small>
      </header>
      <p class="revenue-kpi-meta">
        目標 ${money(target)} · 淨 ${money(net)} · ${progress.toFixed(1)}% · 差 ${money(remaining)}
        · 成交 ${Number(monthly.trade_count || 0)} 筆
      </p>
    </div>
  `
    : `
    <div class="revenue-kpi ${tone}">
      <header>
        <strong>合約月營收目標</strong>
        <small>資金池 ${money(equity)} · 僅 U 本位</small>
      </header>
      <div class="revenue-kpi-grid">
        <div><span>月目標 (⅓權益)</span><strong>${money(target)}</strong></div>
        <div><span>本月淨利</span><strong>${money(net)}</strong></div>
        <div><span>進度</span><strong>${progress.toFixed(1)}%</strong></div>
        <div><span>尚差</span><strong>${money(remaining)}</strong></div>
      </div>
      <p class="revenue-kpi-meta">
        需月化約 ${reqPct.toFixed(1)}% · 階段 ${stage}/4 · 成交 ${Number(monthly.trade_count || 0)} 筆
        ${plan.honest_note ? ` · ${escapeHtml(plan.honest_note)}` : ""}
      </p>
    </div>
  `;
}
