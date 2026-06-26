import {
  fmtStage3Money,
  fmtStage3Value,
  metricRow,
  phaseLabel,
  phaseTone,
  safetyBadge,
  shortCommit,
} from "../utils/stage3_presentation.js?v=20260626a";

function card(title, bodyHtml, tone = "") {
  return `
    <article class="status-card status-card--primary stage3-card ${tone}">
      <span>${title}</span>
      ${bodyHtml}
    </article>
  `;
}

function cardGrid(rows) {
  return `<div class="stage3-card-grid">${rows}</div>`;
}

export function renderStage3TopStatusBar(root, payload) {
  if (!root || !payload) return;

  const deploy = payload.deploy || {};
  const account = payload.account || {};
  const runner = payload.runner || {};
  const learning = payload.learning || {};
  const safety = payload.safety || {};
  const stop = payload.stop || {};
  const phase = phaseLabel(payload.runner_phase);
  const tone = phaseTone(phase, payload);

  root.className = `top-status-bar stage3-top-status-bar ${tone}`;
  root.innerHTML = `
    <div class="status-board">
      <div class="status-primary-grid">
        ${card(
          "Stage 3 狀態",
          cardGrid([
            metricRow("startup_mode", deploy.startup_mode || payload.startup_mode),
            metricRow("runner_started_24h", payload.runner_started_24h),
            metricRow("run_completed", payload.run_completed),
            metricRow("current_status", payload.current_status),
          ]),
          tone,
        )}
        ${card(
          "Bybit Demo Account",
          cardGrid([
            metricRow("equity", fmtStage3Money(account.account_total_equity)),
            metricRow("available", fmtStage3Money(account.account_available_balance)),
            metricRow("wallet", fmtStage3Money(account.account_wallet_balance)),
            metricRow("margin", fmtStage3Money(account.used_margin)),
            metricRow("uPnL", fmtStage3Money(account.unrealized_pnl)),
          ]),
        )}
        ${card(
          "24h Runner",
          cardGrid([
            metricRow("started", runner.started_at_utc),
            metricRow("target min", runner.duration_minutes_target),
            metricRow("elapsed min", runner.elapsed_minutes),
            metricRow("orders", `${runner.orders_sent || 0}/${runner.max_orders_per_day || 6}`),
            metricRow("closed", runner.orders_closed),
            metricRow("open pos", `${runner.open_positions_current ?? runner.open_positions_after ?? 0}`),
          ]),
        )}
        ${card(
          "Learning Evidence",
          cardGrid([
            metricRow("trades", learning.trade_results_count),
            metricRow("reflections", learning.reflection_records_count),
            metricRow("patches", learning.applied_learning_patches_count),
            metricRow("loss trades", learning.loss_trade_count),
            metricRow("loss w/o reflection", learning.loss_without_reflection_count),
            metricRow("repeat detected", learning.repeated_mistake_detected_count),
            metricRow("repeat blocked", learning.repeated_mistake_blocked_count),
          ]),
        )}
        ${card(
          "Safety Gates",
          `<div class="stage3-safety-badges">
            ${safetyBadge("mainnet=false", !safety.bybit_mainnet_allowed)}
            ${safetyBadge("real_money=false", !safety.real_money)}
            ${safetyBadge("live=false", !safety.live_trading)}
            ${safetyBadge("prod_promo=false", !safety.production_promotion_allowed)}
            ${safetyBadge("arm=false", !safety.arm_allowed)}
          </div>
          ${cardGrid([
            metricRow("max_margin_usd", safety.max_margin_usd),
            metricRow("max_leverage", safety.max_leverage),
            metricRow("max_open_positions", safety.max_open_positions),
          ])}`,
        )}
        ${card(
          "Stop Conditions",
          cardGrid([
            metricRow("triggered", (stop.stop_conditions_triggered || []).join(", ") || "—"),
            metricRow("validator_passed", stop.validator_passed),
            metricRow("reconciliation", stop.reconciliation_status),
            metricRow("manual_review", stop.requires_manual_review),
          ]),
          stop.requires_manual_review ? "warn" : tone,
        )}
      </div>
      <footer class="stage3-deploy-strip">
        <small>GitHub Branch: ${fmtStage3Value(deploy.github_branch)}</small>
        <small>Deploy Commit: ${fmtStage3Value(shortCommit(deploy.deploy_commit))}</small>
        <small>Contains 24h Runner: ${fmtStage3Value(deploy.contains_24h_runner)}</small>
        <small>Startup Mode: ${fmtStage3Value(deploy.startup_mode || payload.startup_mode)}</small>
        <small>READ ONLY · Bybit Demo/Testnet · ${fmtStage3Value(phase)}</small>
      </footer>
    </div>
  `;
}
