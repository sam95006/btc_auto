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
  const binanceSpot = capital.binance_spot || {};
  const binanceFutures = capital.binance_futures || {};
  const treasuryAssets = capital.treasury_assets || binanceSpot.treasury_assets || ["USDT"];
  const usdtOnly = treasuryAssets.length === 1 && treasuryAssets[0] === "USDT";
  const spotStable = Number(
    binanceSpot.stable_total ?? capital.spot_stable_total ?? capital.spot_usdt_total ?? 0,
  );
  const spotUsdt = Number(binanceSpot.usdt_total ?? capital.spot_usdt_total ?? 0);
  const spotUsdc = Number(binanceSpot.usdc_total ?? capital.spot_usdc_total ?? 0);
  const spotHoldings = Number(capital.spot_holdings_total ?? binanceSpot.holdings_total ?? 0);
  const futuresWallet = Number(
    binanceFutures.wallet_balance ?? capital.futures_exchange_wallet_balance ?? capital.futures_wallet_display ?? 0,
  );
  const futuresEquity = Number(
    binanceFutures.margin_balance ?? capital.futures_exchange_margin_balance ?? 0,
  );
  const binding = capital.account_binding || {};
  const accountsMismatch = Boolean(binding.accounts_mismatch);
  const tradeCount = Number(decision.trade_count || 0);
  const livePositions = Number(decision.live_position_count || 0);
  const positionSymbols = (decision.exchange_position_symbols || []).filter(Boolean);
  const positionNote = positionSymbols.length ? ` / ${positionSymbols.join(", ")}` : "";
  const systemLabel = system.trading_paused ? "暫停中" : "運行中";
  const capitalSource = capital.source === "binance_rest" ? "Binance 已同步" : "等待 Binance 同步";
  const linkLabel = transport.connected ? capitalSource : "資料連線中斷";
  const mismatchNote = accountsMismatch ? " / 現貨與合約 API 為不同帳戶" : "";
  const holdingsNote = spotHoldings > 0 ? ` / 持倉幣估值 ${formatMoney(spotHoldings)} 不計入` : "";
  const health = state.trading_health || {};
  const healthScore = Number(health.overall_score || 0);
  const healthGrade = health.grade || "--";
  const healthNote = healthScore >= 80 ? `AI 健康 ${healthScore.toFixed(0)} (${healthGrade})` : `AI 強化中 ${healthScore.toFixed(0)} (${healthGrade})`;
  const liveSync = state.live_sync || {};
  const syncNote = liveSync.updated_at ? ` / 資料 ${shortTime(liveSync.updated_at)}` : "";
  const worldNote = liveSync.news_count ? ` / 全球新聞 ${liveSync.news_count} 則` : "";
  const systemMeta = `${linkLabel}${syncNote}${worldNote} / ${healthNote}${mismatchNote} / 持倉 ${livePositions}${positionNote} / 成交 ${tradeCount} 筆${holdingsNote}`;
  const dualTime = `台北 ${shortTime(times.taipei || system.current_time)} | 美東 ${shortTime(times.eastern)}`;

  root.innerHTML = `
    <div class="status-board">
      <div class="status-primary-grid status-primary-grid--compact">
        ${card("總資產", formatMoney(capital.total), usdtOnly ? "僅 USDT（不含 USDC/BTC/幣本位）" : "現貨 + U本位")}
        ${card(
          usdtOnly ? "現貨 USDT" : "現貨穩定幣",
          formatMoney(spotStable),
          usdtOnly ? `可用於現貨交易` : `USDT ${formatMoney(spotUsdt)} / USDC ${formatMoney(spotUsdc)}`,
        )}
        ${card(
          "U本位 USDT",
          formatMoney(futuresEquity),
          `錢包 ${formatMoney(futuresWallet)} / 未實現 ${formatMoney(futuresUnrealized)}`,
          toneClass(futuresUnrealized),
        )}
        ${card("未實現損益", formatMoney(futuresUnrealized), dualTime, toneClass(futuresUnrealized))}
        ${card("系統狀態", systemLabel, systemMeta, system.trading_paused ? "bad" : "good")}
      </div>
    </div>
  `;
}
