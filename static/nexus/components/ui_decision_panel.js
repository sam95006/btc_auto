import { escapeHtml } from "../utils/presentation.js?v=20260526f";

function sourceLabel(item) {
  return item.decision_source || item.proposer || item.source || "system";
}

function pauseReasonLabel(reason) {
  const key = String(reason || "").trim().toLowerCase();
  const map = {
    consecutive_losses: "連續虧損達風控上限（已改為警示，可恢復交易）",
    validation_choke: "驗證拒絕率過高",
    exchange_sync_stale: "交易所同步延遲",
    daily_max_loss: "日損上限",
    manual: "手動暫停",
    news: "新聞熔斷",
    quality_gate_weak_window: "品質窗偏弱（探索模式已放寬）",
    rotation_tighten: "輪換收緊（探索模式已放寬）",
    recent_validation_blocks_too_many: "近期驗證拒絕過多",
    same_side_concentration_too_high: "同向倉位過集中",
    quality_below_growth_threshold: "品質分未達門檻",
  };
  for (const [token, label] of Object.entries(map)) {
    if (key.includes(token)) return label;
  }
  return reason || "未知原因";
}

function rejectReasonLabel(reason) {
  const key = String(reason || "").trim().toLowerCase();
  const map = {
    recent_validation_blocks_too_many: "驗證拒絕累積",
    recent_validation_blocks_caution: "驗證拒絕偏多（警示）",
    same_side_concentration_too_high: "同向集中",
    quality_below_growth_threshold: "品質不足",
    quality_gate_weak_window: "弱窗品質",
    rotation_tighten: "輪換收緊",
    growth_guard_block: "成長護欄",
    decision_quality_ok: "通過",
    approved: "通過",
    historical_edge_too_weak: "歷史優勢不足",
    historical_edge_caution: "歷史偏弱（高信心放行）",
    recent_loss_streak: "連虧紀錄",
    recent_loss_streak_caution: "連虧中（高信心試單）",
    learning_liquidation_cooldown: "強平冷卻",
    learning_symbol_cooldown: "標的冷卻",
    validated_for_execution: "已通過驗證",
    sandbox_backtest_bootstrap: "沙盒試單",
    fee_churn_margin_too_small: "單筆太小",
    fee_churn_notional_too_small: "名義值不足",
    fee_churn_symbol_reopen_cooldown: "平倉冷卻中",
    fee_churn_expected_edge_too_small: "預期獲利不足付手續費",
    daily_loss_limit_reached: "日損上限",
  };
  for (const [token, label] of Object.entries(map)) {
    if (key.includes(token)) return label;
  }
  return reason || "—";
}

function funnelBar(stages) {
  const proposals = Number(stages.proposals || 0);
  const approved = Number(stages.audit_approved || 0);
  const executed = Number(stages.executed_futures_closes || stages.executed || 0);
  const maxVal = Math.max(proposals, 1);
  const pct = (value) => Math.round((value / maxVal) * 100);
  return `
    <div class="decision-funnel-bar" role="img" aria-label="決策漏斗">
      <div class="decision-funnel-step">
        <span>提案</span>
        <div class="decision-funnel-track"><i style="width:${pct(proposals)}%"></i></div>
        <strong>${proposals}</strong>
      </div>
      <div class="decision-funnel-step">
        <span>核准</span>
        <div class="decision-funnel-track"><i style="width:${pct(approved)}%"></i></div>
        <strong>${approved}</strong>
      </div>
      <div class="decision-funnel-step">
        <span>成交</span>
        <div class="decision-funnel-track"><i class="decision-funnel-track--exec" style="width:${pct(executed)}%"></i></div>
        <strong>${executed}</strong>
      </div>
    </div>
  `;
}

export function renderDecisionStrip(root, state, options = {}) {
  if (!root) return;
  const compact = Boolean(options.compact);
  const audits = list(state.decision_audit || [], compact ? 3 : 6);
  const traces = list(state.decision_traces || [], 3);
  const evolution = state.strategy_evolution || {};
  const positionAi = state.position_ai || {};
  const funnel = state.decision_funnel || {};
  const stages = funnel.stages || {};
  const topRejects = (funnel.top_reject_reasons || []).slice(0, 4);

  const rows = audits
    .map((item) => {
      const ok = Boolean(item.approved);
      const symbol = escapeHtml(item.symbol || "--");
      const fleet = escapeHtml(item.fleet || "--");
      const source = escapeHtml(String(sourceLabel(item)));
      const rawReason = item.reject_reason || item.reason || (ok ? "approved" : "blocked");
      const reason = escapeHtml(rejectReasonLabel(rawReason));
      return `<li class="decision-row ${ok ? "ok" : "block"}">
        <span class="decision-row-main">${fleet} · ${symbol}</span>
        <small>${source} · ${reason}</small>
      </li>`;
    })
    .join("");

  const traceNote =
    traces.length > 0
      ? `trace ${escapeHtml(traces[0].trace_id || traces[0].id || "latest")}`
      : "尚無 trace";
  const evoMode = escapeHtml(evolution.evolution_mode || evolution.mode || "hold");
  const posActions = Number((positionAi.actions || []).length || 0);
  const hasFunnel = Number(stages.proposals || 0) > 0;

  const system = state.system || {};
  const paused = Boolean(system.trading_paused);
  const pauseReason = String(system.pause_reason || "").trim();
  const blockReason = String(system.block_reason || "").trim();
  const runningDot = paused ? "pause" : system.block_new_entries ? "warn" : "ok";

  let statusBanner = "";
  if (paused) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--pause">⏸ ${escapeHtml(
      pauseReasonLabel(pauseReason),
    )}</div>`;
  } else if (system.block_new_entries && blockReason) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--warn">⚠ 運行中但擋新倉：${escapeHtml(
      pauseReasonLabel(blockReason),
    )}</div>`;
  } else if (funnel.diagnosis && !paused) {
    statusBanner = `<div class="decision-status-banner decision-status-banner--warn">${escapeHtml(
      compact ? String(funnel.diagnosis).slice(0, 140) : funnel.diagnosis,
    )}</div>`;
  }

  const chips = [
    `<span class="decision-chip">演化 ${evoMode}</span>`,
    `<span class="decision-chip">管倉 ${posActions}</span>`,
  ];
  if (topRejects.length) {
    chips.push(
      `<span class="decision-chip decision-chip--reject">拒絕 ${escapeHtml(
        topRejects.map((r) => rejectReasonLabel(r.reason)).join(" · "),
      )}</span>`,
    );
  }

  let host = root.querySelector(".decision-strip-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "decision-strip-host";
    root.appendChild(host);
  }
  host.dataset.scrollKey = "decision-strip";
  host.innerHTML = `
    <div class="decision-strip decision-strip--premium">
      <header class="decision-strip-head">
        <div class="decision-strip-title">
          <span class="decision-live-dot decision-live-dot--${runningDot}" aria-hidden="true"></span>
          <strong>決策稽核</strong>
        </div>
        <small>${traceNote}</small>
        <div class="decision-meta-chips">${chips.join("")}</div>
      </header>
      ${hasFunnel ? funnelBar(stages) : ""}
      ${statusBanner}
      <ul class="decision-list">${rows || "<li class='decision-row decision-row--empty'>尚無決策樣本</li>"}</ul>
      ${compact && audits.length > 2 ? `<button type="button" class="decision-more-btn" data-decision-expand>展開更多紀錄</button>` : ""}
    </div>
  `;
  if (compact) {
    host.querySelector("[data-decision-expand]")?.addEventListener("click", () => {
      renderDecisionStrip(root, state, { compact: false });
    });
  }
}

function list(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}
