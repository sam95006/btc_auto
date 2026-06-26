import { escapeHtml } from "../utils/presentation.js?v=20260510a";
import { fmtStage3Money, fmtStage3Utc, fmtStage3Value, phaseLabel, phaseTone } from "../utils/stage3_presentation.js?v=20260626a";

export function renderStage3AlertPanel(root, payload) {
  if (!root || !payload) return;

  const runner = payload.runner || {};
  const stop = payload.stop || {};
  const learning = payload.learning || {};
  const phase = phaseLabel(payload.runner_phase);
  const tone = phaseTone(phase, payload);
  const triggered = Array.isArray(stop.stop_conditions_triggered) ? stop.stop_conditions_triggered : [];
  const alertNote = triggered.length
    ? `Stop: ${triggered.join(", ")}`
    : stop.requires_manual_review
      ? "需要人工複核"
      : payload.data_available
        ? "Stage 3 demo learning · read-only"
        : "等待 Stage 3 資料同步";

  root.className = `alert-panel stage3-alert-panel ${tone}${stop.requires_manual_review ? " warn" : ""}`;
  root.dataset.scrollKey = "stage3-alert-panel";
  root.innerHTML = `
    <div class="alert-orb"></div>
    <div class="alert-health">
      <span>Stage 3 24h Demo Runner</span>
      <strong>${escapeHtml(phase)}</strong>
      <small class="alert-health-grade ${tone}">
        orders ${fmtStage3Value(runner.orders_sent)}/${fmtStage3Value(runner.max_orders_per_day)}
        · open ${fmtStage3Value(runner.open_positions_current ?? runner.open_positions_after ?? 0)}
      </small>
      <div class="stage3-alert-metrics">
        <small>latest_order_id: ${fmtStage3Value(runner.latest_order_id)}</small>
        <small>latest_close_pnl: ${fmtStage3Money(runner.latest_close_pnl)}</small>
        <small>latest_reflection: ${fmtStage3Utc(learning.latest_reflection_created)}</small>
        <small>latest_patch: ${fmtStage3Utc(learning.latest_patch_created)}</small>
        <small>stop_conditions: ${fmtStage3Value(triggered.length ? triggered.join(", ") : false)}</small>
      </div>
      <small class="alert-health-tip">${escapeHtml(alertNote)}</small>
    </div>
  `;
}
