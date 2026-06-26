import { escapeHtml } from "./presentation.js?v=20260510a";

export function fmtStage3Value(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  return escapeHtml(String(value));
}

export function fmtStage3Money(value) {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return fmtStage3Value(value);
  return `${num.toFixed(2)} USDT`;
}

export function fmtStage3Utc(value) {
  if (!value) return "—";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return fmtStage3Value(value);
    return d.toLocaleString("zh-TW", { hour12: false });
  } catch {
    return fmtStage3Value(value);
  }
}

export function shortCommit(commit) {
  const text = String(commit || "");
  if (!text || text === "unknown") return "unknown";
  return text.length > 12 ? text.slice(0, 12) : text;
}

export function phaseTone(phase, payload = {}) {
  const stop = payload.stop || {};
  const alerts = payload.alerts || {};
  const safety = payload.safety || {};
  if (
    alerts.mainnet_detected ||
    alerts.real_money_detected ||
    alerts.production_detected ||
    safety.bybit_mainnet_allowed ||
    safety.real_money ||
    safety.live_trading
  ) {
    return "bad";
  }
  if (stop.requires_manual_review) return "warn";
  const normalized = String(phase || "IDLE").toUpperCase();
  if (normalized === "RUNNING") return "good";
  if (normalized === "COMPLETED") return "ok";
  if (normalized === "STOPPED") return "bad";
  return "idle";
}

export function phaseLabel(phase) {
  return String(phase || "IDLE").toUpperCase();
}

export function safetyBadge(label, denied) {
  const tone = denied ? "is-deny" : "is-ok";
  return `<span class="stage3-safety-badge ${tone}">${escapeHtml(label)}</span>`;
}

export function metricRow(label, value) {
  return `<div class="stage3-metric"><span>${escapeHtml(label)}</span><strong>${fmtStage3Value(value)}</strong></div>`;
}
