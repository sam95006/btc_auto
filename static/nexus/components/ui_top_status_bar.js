function formatMoney(value) {
  return `${Number(value || 0).toFixed(2)}U`;
}

function shortTime(value) {
  if (!value || typeof value !== "string") return "--:--";
  return value.length >= 16 ? value.slice(11, 16) : value;
}

function toneClass(value) {
  const number = Number(value || 0);
  if (number > 0) return "good";
  if (number < 0) return "bad";
  return "";
}

function card(label, value, meta = "", tone = "") {
  return `
    <article class="status-card status-card--primary ${tone}">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${meta}</small>
    </article>
  `;
}

export function renderTopStatusBar(root, state) {
  if (!root) return;

  const transport = state.transport || {};
  const capital = state.capital || {};
  const pnl = state.pnl || {};
  const system = state.system || {};
  const decision = state.decision_summary || {};
  const overview = state.market_overview || {};
  const times = overview.times || {};

  const totalPnl = Number(pnl.total_pnl || 0);
  const futuresUnrealized = Number(capital.futures_unrealized_pnl || 0);
  const tradeCount = Number(decision.trade_count || 0);
  const systemLabel = system.trading_paused ? "暫停中" : "運行中";
  const linkLabel = transport.connected ? "資料連線正常" : "資料連線中斷";
  const systemMeta = `${linkLabel} / 成交 ${tradeCount} 筆`;
  const dualTime = `台北 ${shortTime(times.taipei || system.current_time)} | 美東 ${shortTime(times.eastern)}`;

  root.innerHTML = `
    <div class="status-board">
      <div class="status-primary-grid status-primary-grid--compact">
        ${card("總資產", formatMoney(capital.total), "全站帳戶合計")}
        ${card("現貨資金", formatMoney(capital.spot_total), "HQ Spot 帳戶")}
        ${card("合約資金", formatMoney(capital.futures_total), `未實現 ${formatMoney(futuresUnrealized)}`, toneClass(futuresUnrealized))}
        ${card("總損益", formatMoney(totalPnl), dualTime, toneClass(totalPnl))}
        ${card("系統狀態", systemLabel, systemMeta, system.trading_paused ? "bad" : "good")}
      </div>
    </div>
  `;
}
