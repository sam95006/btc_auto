import { escapeHtml } from "./presentation.js?v=20260510a";

export function pickExternalIntel(state) {
  const decision = state?.decision_summary || {};
  return decision.external_market_intel || state?.external_market_intel || {};
}

export function pickGrowth(state) {
  return state?.growth_mode || {};
}

export function pickResearchGate(state) {
  const growth = pickGrowth(state);
  return growth.research_gate || state?.research_gate || {};
}

export function pickRegime(state) {
  const growth = pickGrowth(state);
  return growth.regime_classifier || state?.regime || {};
}

export function pickOpsHealth(state) {
  return state?.ops_health || {};
}

function toneForValue(kind, value) {
  if (kind === "fear_greed") {
    const v = Number(value);
    if (v <= 25) return "bad";
    if (v >= 75) return "warn";
    if (v >= 45 && v <= 55) return "good";
    return "ok";
  }
  if (kind === "pass") return value ? "good" : "warn";
  if (kind === "stress") return value ? "bad" : "good";
  return "";
}

export function buildMarketIntelRows(state) {
  const intel = pickExternalIntel(state);
  const growth = pickGrowth(state);
  const fear = intel.fear_greed || growth.fear_greed || {};
  const macro = intel.binance_macro || growth.binance_macro || {};
  const cq = intel.cryptoquant || {};
  const cmc = intel.coinmarketcap || {};
  const research = pickResearchGate(state);
  const regime = pickRegime(state);
  const ops = pickOpsHealth(state);

  const rows = [
    {
      key: "fear_greed",
      label: "恐慌貪婪",
      value: fear.value != null ? `${fear.value} · ${fear.classification || "—"}` : "—",
      tone: toneForValue("fear_greed", fear.value),
      source: "Alternative.me",
    },
    {
      key: "regime",
      label: "市場體制",
      value: regime.label || growth.market_regime_ai || "—",
      meta: regime.source ? `來源 ${regime.source}` : "",
      tone: regime.label === "HIGH_RISK_MACRO" ? "bad" : regime.label === "TREND_BULL" ? "good" : "ok",
      source: "NEXUS Regime",
    },
    {
      key: "research_gate",
      label: "研究閘道",
      value: research.research_pass === false ? "未通過" : research.research_pass === true ? "通過" : "—",
      meta: research.reason || "",
      tone: toneForValue("pass", research.research_pass !== false),
      source: "Walk-forward + K線",
    },
    {
      key: "btc_dominance",
      label: "BTC 市佔",
      value: cmc.btc_dominance != null ? `${Number(cmc.btc_dominance).toFixed(1)}%` : growth.btc_dominance != null ? `${Number(growth.btc_dominance).toFixed(1)}%` : "—",
      tone: cmc.alt_leverage_reduce ? "warn" : "ok",
      source: "CoinMarketCap",
    },
    {
      key: "netflow",
      label: "BTC 淨流入",
      value: cq.btc_exchange_netflow != null ? `${Number(cq.btc_exchange_netflow).toFixed(1)} BTC` : "—",
      tone: cq.netflow_bearish || cq.whale_dump_alert ? "bad" : "good",
      source: "CryptoQuant",
    },
    {
      key: "long_short",
      label: "多空帳戶比",
      value: macro.long_short_account_ratio != null ? Number(macro.long_short_account_ratio).toFixed(3) : "—",
      tone: macro.long_crowded ? "warn" : macro.short_crowded ? "good" : "ok",
      source: "Binance",
    },
    {
      key: "liquidations",
      label: "1h 清算",
      value: macro.recent_liquidation_count != null ? `${macro.recent_liquidation_count} 筆` : "—",
      tone: toneForValue("stress", macro.liquidation_stress),
      source: "Binance",
    },
    {
      key: "spot_premium",
      label: "現貨溢價",
      value: macro.spot_futures_premium_bps != null ? `${Number(macro.spot_futures_premium_bps).toFixed(1)} bps` : "—",
      tone: macro.spot_premium_elevated ? "warn" : "ok",
      source: "Spot vs 合約",
    },
    {
      key: "ops",
      label: "營運 SLO",
      value: ops.slo_score != null ? `${ops.status || "—"} · ${Number(ops.slo_score).toFixed(0)}%` : "—",
      tone: ops.status === "healthy" ? "good" : ops.status === "degraded" ? "warn" : ops.status === "critical" ? "bad" : "ok",
      source: "NEXUS Ops",
    },
  ];
  return rows;
}

export function renderMarketIntelList(rows, limit = 8) {
  const slice = (rows || []).slice(0, limit);
  if (!slice.length) {
    return `<p class="market-intel-empty">尚無外部市場資料。</p>`;
  }
  return `
    <ul class="market-intel-list">
      ${slice
        .map((row) => {
          const meta = row.meta ? `<em>${escapeHtml(row.meta)}</em>` : `<em>${escapeHtml(row.source || "")}</em>`;
          return `
            <li class="market-intel-row ${escapeHtml(row.tone || "")}">
              <span>${escapeHtml(row.label)}</span>
              <strong>${escapeHtml(String(row.value))}</strong>
              ${meta}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

export function renderExternalAlertChips(state, limit = 6) {
  const intel = pickExternalIntel(state);
  const alerts = [...(intel.alerts || []), ...((pickGrowth(state).external_market_intel || {}).alerts || [])];
  const unique = [];
  const seen = new Set();
  for (const raw of alerts) {
    const text = String(raw || "").trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    unique.push(text);
  }
  if (!unique.length) {
    return `<span class="market-intel-chip market-intel-chip--muted">無外部警報</span>`;
  }
  return unique
    .slice(0, limit)
    .map((text) => {
      const tone = /stress|spike|extreme|fail|bearish|liquidation/i.test(text) ? "bad" : "warn";
      const label = text.includes(":") ? text.split(":").slice(1).join(":") : text;
      return `<span class="market-intel-chip market-intel-chip--${tone}" title="${escapeHtml(text)}">${escapeHtml(label.slice(0, 42))}</span>`;
    })
    .join("");
}

export function mergeAlertsForDisplay(state, limit = 8) {
  const runtimeAlerts = Array.isArray(state?.alerts) ? state.alerts : [];
  const intel = pickExternalIntel(state);
  const external = (intel.alerts || []).map((text) => ({
    time: intel.updated_at || "外部",
    level: /stress|spike|extreme|fail/i.test(String(text)) ? "WARNING" : "INFO",
    summary: String(text).replace(/_/g, " "),
    source: "external_market",
  }));
  const merged = [];
  const seen = new Set();
  for (const item of [...external, ...runtimeAlerts]) {
    const key = `${item.time || ""}|${item.summary || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }
  return merged.slice(0, limit);
}

export function renderMarketIntelSection(state, { title = "加密市場情報", subtitle = "鏈上 · 情緒 · 衍生品" } = {}) {
  const rows = buildMarketIntelRows(state);
  return `
    <section class="hq-side-card market-intel-card">
      <header>
        <span>${escapeHtml(subtitle)}</span>
        <strong>${escapeHtml(title)}</strong>
      </header>
      ${renderMarketIntelList(rows, 9)}
      <div class="market-intel-chips">${renderExternalAlertChips(state, 5)}</div>
    </section>
  `;
}
