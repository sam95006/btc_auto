import { escapeHtml } from "../utils/presentation.js?v=20260525a";

function gradeTone(grade) {
  if (grade === "A+" || grade === "A") return "good";
  if (grade === "A-") return "good";
  if (grade === "B") return "ok";
  if (grade === "C") return "warn";
  return "bad";
}

export function renderAlertPanel(root, state) {
  const system = state.system || {};
  const health = state.trading_health || {};
  const radar = state.maturity_radar || health.maturity_radar || {};
  const paused = Boolean(system.trading_paused);
  const blocked = Boolean(system.block_new_entries);
  const title = "系統狀態";
  const detail = paused ? "暫停中" : blocked ? "運行中·控倉" : "運行中";
  const tone = paused ? "warn active" : blocked ? "warn" : "healthy";
  const score = Number(radar.overall_score || health.overall_score || 0);
  const grade = radar.grade || health.grade || "--";
  const approval = Number((health.approval_rate || 0) * 100).toFixed(1);
  const topReject = (health.top_reject_reasons || [])[0];
  const rejectNote = topReject ? `${topReject.label || topReject.reason} ×${topReject.count}` : "無主要拒單";
  const compound = state.compound_capital || (state.growth_mode || {}).compound || {};
  const daily = (state.growth_mode || {}).daily || {};
  const compoundNote = compound.enabled
    ? `復投基準 ${Number(compound.reinvest_base_equity || daily.reinvest_base_equity || 0).toFixed(0)} · 今日 ${daily.is_positive_day ? "正" : "負"}${Number(daily.daily_pnl || 0).toFixed(2)}`
    : "";
  const target90 = radar.target_90_all_dimensions ? " · 五維≥90" : "";
  const tip =
    compoundNote ||
    (radar.recommendations || health.recommendations || [])[0] ||
    "AI 與 Binance 同步正常";
  const dims = radar.dimensions || {};
  const labels = radar.dimension_labels || {};
  const dimRows = Object.keys(dims)
    .map((key) => {
      const value = Number(dims[key] || 0);
      const label = labels[key] || key;
      const dimTone = value >= 80 ? "good" : value >= 65 ? "ok" : "warn";
      return `<small class="maturity-dim ${dimTone}">${escapeHtml(label)} ${value.toFixed(0)}%</small>`;
    })
    .join("");

  root.className = `alert-panel ${tone}`;
  root.dataset.scrollKey = "main-alert-panel";
  root.innerHTML = `
    <div class="alert-orb"></div>
    <div class="alert-health">
      <span>${title}</span>
      <strong>${detail}</strong>
      <small class="alert-health-grade ${gradeTone(grade)}">成熟度 ${score.toFixed(0)} · ${escapeHtml(grade)}</small>
      <div class="maturity-radar-dims">${dimRows}</div>
      <small>核准率 ${approval}% · ${escapeHtml(rejectNote)}</small>
      <small class="alert-health-tip">${escapeHtml(tip)}</small>
    </div>
  `;
}
