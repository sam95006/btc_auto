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

  const totalPnl = Number(pnl.exchange_unrealized_pnl ?? pnl.total_pnl ?? 0);
  const futuresUnrealized = Number(capital.futures_unrealized_pnl || pnl.exchange_unrealized_pnl || 0);
  const spotStable = Number(capital.spot_stable_total || capital.spot_total || 0);
  const spotUsdt = Number(capital.spot_usdt_total || 0);
  const spotUsdc = Number(capital.spot_usdc_total || 0);
  const futuresWallet = Number(
    capital.futures_wallet_display || capital.futures_exchange_wallet_balance || capital.futures_wallet_total || 0,
  );
  const futuresEquity = Number(capital.futures_exchange_margin_balance || capital.futures_total || 0);
  const tradeCount = Number(decision.trade_count || 0);
  const livePositions = Number(decision.live_position_count || 0);
  const systemLabel = system.trading_paused ? "暫停中" : "運行中";
  const linkLabel = transport.connected ? "Binance 已同步" : "資料連線中斷";
  const systemMeta = `${linkLabel} / 持倉 ${livePositions} / 成交 ${tradeCount} 筆`;
  const dualTime = `台北 ${shortTime(times.taipei || system.current_time)} | 美東 ${shortTime(times.eastern)}`;

  root.innerHTML = `
    <div class="status-board">
      <div class="status-primary-grid status-primary-grid--compact">
        ${card("總資產", formatMoney(capital.total), "現貨穩定幣 + 合約權益")}
        ${card("現貨資金", formatMoney(spotStable), `USDT ${formatMoney(spotUsdt)} / USDC ${formatMoney(spotUsdc)}`)}
        ${card("合約資金", formatMoney(futuresEquity), `錢包 ${formatMoney(futuresWallet)} / 未實現 ${formatMoney(futuresUnrealized)}`, toneClass(futuresUnrealized))}
        ${card("未實現損益", formatMoney(futuresUnrealized), dualTime, toneClass(futuresUnrealized))}
        ${card("系統狀態", systemLabel, systemMeta, system.trading_paused ? "bad" : "good")}
      </div>
    </div>
  `;
}
