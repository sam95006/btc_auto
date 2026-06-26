import { escapeHtml } from "../utils/presentation.js?v=20260510a";
import { fetchStage3Status } from "../api_client.js?v=20260626a";
import {
  fmtStage3Money,
  fmtStage3Utc,
  fmtStage3Value,
  metricRow,
  phaseLabel,
  phaseTone,
  safetyBadge,
  shortCommit,
} from "../utils/stage3_presentation.js?v=20260626a";

const UNAVAILABLE_MSG = "Stage 3 demo learning data not available — waiting for /data/stage3_demo_learning";

export async function prefetchStage3Status() {
  return fetchStage3Status();
}

function renderUnavailable(host) {
  host.innerHTML = `
    <div class="stage3-panel stage3-panel--missing">
      <header class="stage3-head">
        <span class="stage3-badge is-off">READ ONLY</span>
        <h3>Stage 3 Demo Learning</h3>
      </header>
      <p class="stage3-unavailable">${escapeHtml(UNAVAILABLE_MSG)}</p>
      <footer class="stage3-foot">
        <small>API: GET /api/nexus/stage3/status</small>
      </footer>
    </div>
  `;
}

function renderEventLog(events, logTail) {
  const eventRows = (Array.isArray(events) ? events : [])
    .slice()
    .reverse()
    .map((row) => {
      const at = fmtStage3Utc(row.at);
      const label = [row.type, row.symbol, row.side].filter(Boolean).join(" · ");
      return `<li><span>${at}</span><strong>${fmtStage3Value(label || row.decision_id)}</strong></li>`;
    })
    .join("");
  const logRows = (Array.isArray(logTail) ? logTail : [])
    .slice()
    .reverse()
    .slice(0, 12)
    .map((line) => `<li class="stage3-log-line">${escapeHtml(line)}</li>`)
    .join("");
  return `
    <section class="stage3-section">
      <h4>Stage 3 Event Log</h4>
      <ul class="stage3-event-list">${eventRows || "<li><span>—</span><strong>尚無事件</strong></li>"}</ul>
      <h4>Runner Log Tail</h4>
      <ul class="stage3-log-list">${logRows || "<li class='stage3-log-line'>尚無 log</li>"}</ul>
    </section>
  `;
}

export function renderStage3Panel(host, payload, { onUpdate } = {}) {
  if (!host) return;
  if (!payload || payload.error) {
    renderUnavailable(host);
    return;
  }

  const deploy = payload.deploy || {};
  const account = payload.account || {};
  const runner = payload.runner || {};
  const learning = payload.learning || {};
  const safety = payload.safety || {};
  const stop = payload.stop || {};
  const phase = phaseLabel(payload.runner_phase);
  const tone = phaseTone(phase, payload);

  host.innerHTML = `
    <div class="stage3-panel">
      <header class="stage3-head">
        <span class="stage3-badge is-readonly">READ ONLY · BYBIT DEMO</span>
        <h3>Stage 3 Demo Learning</h3>
        <p class="stage3-explainer">Bybit Demo/Testnet · 24h Runner · 學習閉環 · 反思 / Patch · 防重複錯誤 · 安全閘門</p>
      </header>

      <section class="stage3-section">
        <h4>Deploy Version</h4>
        <div class="stage3-metrics">
          ${metricRow("GitHub Branch", deploy.github_branch)}
          ${metricRow("Deploy Commit", shortCommit(deploy.deploy_commit))}
          ${metricRow("Contains 24h Runner", deploy.contains_24h_runner)}
          ${metricRow("Startup Mode", deploy.startup_mode || payload.startup_mode)}
          ${metricRow("Runner Phase", phase)}
          ${metricRow("Data Source", payload.output_dir)}
        </div>
      </section>

      <section class="stage3-section">
        <h4>Stage 3 狀態 <span class="stage3-phase ${tone}">${escapeHtml(phase)}</span></h4>
        <div class="stage3-metrics">
          ${metricRow("startup_mode", payload.startup_mode)}
          ${metricRow("runner_started_24h", payload.runner_started_24h)}
          ${metricRow("run_completed", payload.run_completed)}
          ${metricRow("current_status", payload.current_status)}
        </div>
      </section>

      <section class="stage3-section">
        <h4>Bybit Demo Account · 模擬盤資金</h4>
        <div class="stage3-metrics">
          ${metricRow("account_total_equity", fmtStage3Money(account.account_total_equity))}
          ${metricRow("account_available_balance", fmtStage3Money(account.account_available_balance))}
          ${metricRow("account_wallet_balance", fmtStage3Money(account.account_wallet_balance))}
          ${metricRow("used_margin", fmtStage3Money(account.used_margin))}
          ${metricRow("unrealized_pnl", fmtStage3Money(account.unrealized_pnl))}
        </div>
      </section>

      <section class="stage3-section">
        <h4>24h Runner</h4>
        <div class="stage3-metrics">
          ${metricRow("started_at_utc", fmtStage3Utc(runner.started_at_utc))}
          ${metricRow("duration_minutes_target", runner.duration_minutes_target)}
          ${metricRow("elapsed_minutes", runner.elapsed_minutes)}
          ${metricRow("max_orders_per_day", runner.max_orders_per_day)}
          ${metricRow("orders_sent", runner.orders_sent)}
          ${metricRow("orders_closed", runner.orders_closed)}
          ${metricRow("open_positions", runner.open_positions_current ?? runner.open_positions_after ?? 0)}
        </div>
      </section>

      <section class="stage3-section">
        <h4>Learning Evidence · 學習閉環</h4>
        <div class="stage3-metrics">
          ${metricRow("trade_results_count", learning.trade_results_count)}
          ${metricRow("reflection_records_count", learning.reflection_records_count)}
          ${metricRow("applied_learning_patches_count", learning.applied_learning_patches_count)}
          ${metricRow("loss_trade_count", learning.loss_trade_count)}
          ${metricRow("loss_without_reflection_count", learning.loss_without_reflection_count)}
          ${metricRow("repeated_mistake_detected_count", learning.repeated_mistake_detected_count)}
          ${metricRow("repeated_mistake_blocked_count", learning.repeated_mistake_blocked_count)}
        </div>
      </section>

      <section class="stage3-section">
        <h4>Safety Gates · 安全閘門</h4>
        <div class="stage3-safety-badges">
          ${safetyBadge("bybit_mainnet_allowed=false", !safety.bybit_mainnet_allowed)}
          ${safetyBadge("real_money=false", !safety.real_money)}
          ${safetyBadge("live_trading=false", !safety.live_trading)}
          ${safetyBadge("production_promotion_allowed=false", !safety.production_promotion_allowed)}
          ${safetyBadge("arm_allowed=false", !safety.arm_allowed)}
        </div>
        <div class="stage3-metrics">
          ${metricRow("max_margin_usd", safety.max_margin_usd)}
          ${metricRow("max_leverage", safety.max_leverage)}
          ${metricRow("max_open_positions", safety.max_open_positions)}
        </div>
      </section>

      <section class="stage3-section">
        <h4>Stop Conditions</h4>
        <div class="stage3-metrics">
          ${metricRow("stop_conditions_triggered", (stop.stop_conditions_triggered || []).join(", ") || "—")}
          ${metricRow("validator_passed", stop.validator_passed)}
          ${metricRow("reconciliation_status", stop.reconciliation_status)}
          ${metricRow("requires_manual_review", stop.requires_manual_review)}
        </div>
      </section>

      ${renderEventLog(payload.events, payload.log_tail)}

      <footer class="stage3-foot">
        <small>Updated ${fmtStage3Utc(payload.generated_at_utc)}</small>
        <small>Read-only dashboard — no order / ARM / env mutation</small>
      </footer>
    </div>
  `;

  if (typeof onUpdate === "function" && !host.dataset.boundRefresh) {
    host.dataset.boundRefresh = "1";
  }
}
