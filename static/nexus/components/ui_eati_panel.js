import { escapeHtml } from "../utils/presentation.js?v=20260609a";
import { fetchEatiStatusSnapshot } from "../api_client.js?v=20260609a";

const UNAVAILABLE_MSG = "EATI snapshot unavailable — local research data not deployed";

let cache = { status: "idle", snapshot: null };

function fmtUtc(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return escapeHtml(String(iso));
    return d.toLocaleString("zh-TW", { hour12: false });
  } catch {
    return escapeHtml(String(iso));
  }
}

function fmtNull(value) {
  return value === null || value === undefined ? "null" : escapeHtml(String(value));
}

function boolBadge(label, ok) {
  return `<span class="eati-safety-badge ${ok ? "is-ok" : "is-deny"}">${escapeHtml(label)}</span>`;
}

function phaseRow(label, status) {
  const accepted = String(status || "").includes("accepted") || status === "needs_more_paper_data";
  return `<li class="eati-phase-row ${accepted ? "is-ok" : "is-warn"}">
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(String(status || "—"))}</strong>
  </li>`;
}

function renderUnavailable(host) {
  host.innerHTML = `
    <div class="eati-panel eati-panel--missing">
      <header class="eati-head">
        <span class="eati-badge is-off">READ ONLY</span>
        <h3>EATI 訓練所</h3>
      </header>
      <p class="eati-unavailable">${escapeHtml(UNAVAILABLE_MSG)}</p>
      <footer class="eati-foot">
        <small>Static snapshot path: /static/nexus/eati_status_snapshot.json</small>
      </footer>
    </div>
  `;
}

function renderSnapshot(host, snap) {
  const eati = snap.eati_status || {};
  const pa = snap.paper_accumulation || {};
  const safety = snap.safety || {};
  const warnings = Array.isArray(snap.warnings) ? snap.warnings : [];

  host.innerHTML = `
    <div class="eati-panel">
      <header class="eati-head">
        <span class="eati-badge is-readonly">READ ONLY · NOT LIVE</span>
        <h3>EATI 訓練所</h3>
        <p class="eati-explainer">External Alpha Training Institute — paper research lane only</p>
      </header>

      <section class="eati-section">
        <h4>Mode</h4>
        <div class="eati-metrics">
          <div><span>Mode</span><strong>${escapeHtml(snap.mode || "—")}</strong></div>
          <div><span>Cloud deployed</span><strong>${snap.cloud_deployed ? "true" : "false"}</strong></div>
          <div><span>Production connected</span><strong>${snap.production_connected ? "true" : "false"}</strong></div>
          <div><span>Production impact</span><strong>${escapeHtml(snap.production_impact || "none")}</strong></div>
        </div>
      </section>

      <section class="eati-section">
        <h4>Phase status</h4>
        <ul class="eati-phase-list">
          ${phaseRow("Phase 1", eati.phase1)}
          ${phaseRow("Phase 2", eati.phase2)}
          ${phaseRow("Phase 3", eati.phase3)}
          ${phaseRow("Phase 4", eati.phase4)}
          ${phaseRow("Phase 5", eati.phase5)}
          ${phaseRow("Phase 6", eati.phase6)}
          ${phaseRow("Phase 7", eati.phase7)}
          ${phaseRow("Phase 8", eati.phase8)}
          ${phaseRow("Phase 9", eati.phase9)}
        </ul>
      </section>

      <section class="eati-section">
        <h4>Paper accumulation</h4>
        <div class="eati-metrics">
          <div><span>Day</span><strong>${Number(pa.current_day_index || 0)} / ${Number(pa.required_days || 14)}</strong></div>
          <div><span>Paper signals</span><strong>${Number(pa.total_paper_signals || 0)} / ${Number(pa.required_signals || 14)}</strong></div>
          <div><span>Would skip</span><strong>${Number(pa.would_skip_count || 0)}</strong></div>
          <div><span>Would enter</span><strong>${Number(pa.would_enter_count || 0)} / ${Number(pa.required_would_enter || 3)}</strong></div>
          <div><span>Context similarity</span><strong>${fmtNull(pa.context_similarity_score)}</strong></div>
          <div><span>Quarantine</span><strong>${Number(pa.quarantine_count || 0)}</strong></div>
          <div><span>Phase 8 eligible</span><strong>${pa.phase8_rerun_eligible ? "true" : "false"}</strong></div>
          <div><span>Production promotion</span><strong>${pa.production_promotion_allowed ? "allowed" : "denied"}</strong></div>
        </div>
      </section>

      <section class="eati-section">
        <h4>Safety</h4>
        <div class="eati-safety-badges">
          ${boolBadge("NOT LIVE TRADING", !safety.is_live_trading)}
          ${boolBadge("NO ARM", !safety.arm_allowed)}
          ${boolBadge("NO MICRO VALIDATION", !safety.micro_validation_allowed)}
          ${boolBadge("NO PRODUCTION PROMOTION", !safety.production_promotion_allowed)}
          ${boolBadge("READ ONLY", true)}
        </div>
      </section>

      <section class="eati-section">
        <h4>Warnings</h4>
        <ul class="eati-warnings">
          ${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("") || "<li>—</li>"}
        </ul>
      </section>

      <footer class="eati-foot">
        <small>Snapshot: ${fmtUtc(snap.generated_at_utc)} UTC</small>
        <small>Source: static/nexus/eati_status_snapshot.json</small>
      </footer>
    </div>
  `;
}

function renderLoading(host) {
  host.innerHTML = `
    <div class="eati-panel eati-panel--loading">
      <header class="eati-head">
        <span class="eati-badge is-readonly">READ ONLY</span>
        <h3>EATI 訓練所</h3>
      </header>
      <p class="eati-explainer">Loading snapshot…</p>
    </div>
  `;
}

export function prefetchEatiSnapshot() {
  if (cache.status !== "idle") return Promise.resolve(cache);
  cache = { status: "loading", snapshot: null };
  return fetchEatiStatusSnapshot()
    .then((snapshot) => {
      cache = { status: "ok", snapshot };
      return cache;
    })
    .catch(() => {
      cache = { status: "missing", snapshot: null };
      return cache;
    });
}

export function renderEatiPanel(root, { onUpdate } = {}) {
  if (!root) return;

  let host = root.querySelector(".eati-panel-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "eati-panel-host";
    root.appendChild(host);
  }

  if (cache.status === "idle") {
    renderLoading(host);
    prefetchEatiSnapshot().then(() => {
      if (typeof onUpdate === "function") onUpdate();
    });
    return;
  }

  if (cache.status === "loading") {
    renderLoading(host);
    return;
  }

  if (cache.status === "missing" || !cache.snapshot) {
    renderUnavailable(host);
    return;
  }

  renderSnapshot(host, cache.snapshot);
}

export function resetEatiPanelCache() {
  cache = { status: "idle", snapshot: null };
}
