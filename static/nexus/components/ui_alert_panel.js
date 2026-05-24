import { escapeHtml } from "../utils/presentation.js?v=20260525a";

function gradeTone(grade) {
  if (grade === "A") return "good";
  if (grade === "B") return "ok";
  if (grade === "C") return "warn";
  return "bad";
}

export function renderAlertPanel(root, state) {
  const system = state.system || {};
  const health = state.trading_health || {};
  const paused = Boolean(system.trading_paused);
  const title = "系統狀態";
  const detail = paused ? "暫停中" : "運行中";
  const tone = paused ? "warn active" : "healthy";
  const score = Number(health.overall_score || 0);
  const grade = health.grade || "--";
  const approval = Number((health.approval_rate || 0) * 100).toFixed(1);
  const topReject = (health.top_reject_reasons || [])[0];
  const rejectNote = topReject ? `${topReject.label || topReject.reason} ×${topReject.count}` : "無主要拒單";
  const tip = (health.recommendations || [])[0] || "AI 與 Binance 同步正常";

  root.className = `alert-panel ${tone}`;
  root.dataset.scrollKey = "main-alert-panel";
  root.innerHTML = `
    <div class="alert-orb"></div>
    <div class="alert-health">
      <span>${title}</span>
      <strong>${detail}</strong>
      <small class="alert-health-grade ${gradeTone(grade)}">健康 ${score.toFixed(0)} · ${escapeHtml(grade)}</small>
      <small>核准率 ${approval}% · ${escapeHtml(rejectNote)}</small>
      <small class="alert-health-tip">${escapeHtml(tip)}</small>
    </div>
  `;
}
