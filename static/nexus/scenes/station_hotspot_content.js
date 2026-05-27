import { escapeHtml, normalizeText } from "../utils/presentation.js?v=20260510a";

const FLEET_SYMBOL_KEYWORDS = {
  BTC: ["bitcoin", "btc"],
  ETH: ["ethereum", "eth"],
  SOL: ["solana", "sol"],
  PEPE: ["pepe", "1000pepe"],
};

export function radarWhaleRows(state) {
  const scan = state.radar_scan || {};
  const fromScan = Array.isArray(scan.whale_watch) ? scan.whale_watch : [];
  const fromWhale = Array.isArray(state.whale?.watch) ? state.whale.watch : [];
  const merged = [...fromScan, ...fromWhale];
  const seen = new Set();
  const rows = [];
  for (const item of merged) {
    const symbol = String(item.symbol || "").toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    rows.push(item);
  }
  return rows.sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0));
}

export function renderRadarWhaleHtml(state, emptyText = "目前沒有偵測到巨鯨級別的訂單簿／資金費率異常。") {
  const rows = radarWhaleRows(state);
  const status = String(state.radar_scan?.scan_status || "idle");
  const generatedAt = state.radar_scan?.generated_at || state.whale?.generated_at || "--";

  if (!rows.length) {
    return `
      <p style="color:rgba(255,255,255,0.45);font-size:12px;margin:0 0 8px;">
        掃描狀態：${escapeHtml(status)} · 更新 ${escapeHtml(generatedAt)}
      </p>
      <p style="color:rgba(255,255,255,0.4);font-size:12px;">${escapeHtml(emptyText)}</p>
      <p style="color:rgba(255,255,255,0.35);font-size:11px;margin-top:8px;">
        資料來源：Binance 合約即時訂單簿失衡、資金費率與基差（非鏈上錢包追蹤）。
      </p>
    `;
  }

  const cards = rows.slice(0, 12).map((item) => {
    const fundingPct = (Number(item.funding_rate || 0) * 100).toFixed(4);
    const basis = Number(item.basis_bps || 0).toFixed(2);
    const bias = normalizeText(item.bias, "balanced");
    const summary = normalizeText(item.summary, "異常偏斜");
    return `
      <article style="background:rgba(255,255,255,0.04);border:1px solid rgba(79,216,255,0.14);border-radius:10px;padding:12px 14px;margin-bottom:10px;">
        <b style="color:var(--cyan);font-size:13px;">${escapeHtml(String(item.symbol || "--"))}</b>
        <p style="margin:6px 0 4px;font-size:12px;line-height:1.55;color:rgba(238,250,255,0.92);">
          巨鯨訊號：${escapeHtml(summary)} · 訂單簿 ${escapeHtml(bias)}
        </p>
        <small style="display:block;color:rgba(255,255,255,0.55);font-size:11px;">
          資金費率 ${fundingPct}% · 基差 ${basis} bps · 優先度 ${Number(item.priority || 0).toFixed(1)}
        </small>
      </article>
    `;
  }).join("");

  return `
    <p style="color:rgba(255,255,255,0.45);font-size:12px;margin:0 0 10px;">
      即時掃描 ${rows.length} 檔 · 狀態 ${escapeHtml(status)} · ${escapeHtml(generatedAt)}
    </p>
    ${cards}
    <p style="color:rgba(255,255,255,0.35);font-size:11px;margin-top:6px;">
      資料來源：Binance 合約市場微結構（訂單簿失衡 ≥35%、基差或資金費率偏離閾值）。
    </p>
  `;
}

export function radarFundingRows(state) {
  const board = Array.isArray(state.radar_scan?.market_board) ? state.radar_scan.market_board : [];
  const rows = board.map((item) => ({
    symbol: item.symbol,
    funding_rate: item.funding_rate,
    basis_bps: item.basis_bps,
    mark_price: item.mark_price,
    source: "radar_scan",
  }));

  const marketContext = state.market_context || {};
  for (const fleet of ["BTC", "ETH", "SOL", "PEPE"]) {
    const ctx = marketContext[fleet] || {};
    const symbol = String(ctx.symbol || "").toUpperCase();
    if (!symbol) continue;
    if (rows.some((row) => String(row.symbol).toUpperCase() === symbol)) continue;
    rows.push({
      symbol,
      funding_rate: ctx.funding_rate,
      basis_bps: ctx.basis_bps,
      mark_price: ctx.mark_price,
      source: `fleet_${fleet}`,
    });
  }

  return rows
    .filter((item) => item.symbol)
    .sort((a, b) => Math.abs(Number(b.funding_rate || 0)) - Math.abs(Number(a.funding_rate || 0)));
}

export function renderRadarFundingHtml(state, emptyText = "目前沒有資金費率資料。") {
  const rows = radarFundingRows(state);
  if (!rows.length) {
    return `<p style="color:rgba(255,255,255,0.4);font-size:12px;">${escapeHtml(emptyText)}</p>`;
  }

  const cards = rows.slice(0, 14).map((item) => {
    const rate = Number(item.funding_rate || 0);
    const ratePct = (rate * 100).toFixed(4);
    const tone = rate > 0 ? "rgba(255,120,120,0.9)" : rate < 0 ? "rgba(120,255,180,0.9)" : "rgba(255,255,255,0.7)";
    return `
      <article style="background:rgba(255,255,255,0.04);border:1px solid rgba(120,200,255,0.12);border-radius:10px;padding:10px 12px;margin-bottom:8px;">
        <b style="color:var(--cyan);font-size:12px;">${escapeHtml(String(item.symbol))}</b>
        <span style="float:right;color:${tone};font-size:12px;">${ratePct}%</span>
        <small style="display:block;color:rgba(255,255,255,0.5);font-size:11px;margin-top:4px;">
          基差 ${Number(item.basis_bps || 0).toFixed(2)} bps · 標記 ${Number(item.mark_price || 0).toFixed(4)} · ${escapeHtml(item.source)}
        </small>
      </article>
    `;
  }).join("");

  return cards;
}

function inferNewsBucket(item) {
  const explicit = String(item.bucket || "").toLowerCase();
  if (explicit) return explicit;
  const haystack = `${item.category || ""} ${item.title || ""} ${item.summary || ""}`.toLowerCase();
  if (/fed|fomc|powell|federal reserve|sec.*etf|rate (cut|hike)/i.test(haystack)) return "fed";
  if (/cpi|pce|gdp|inflation|jobs|treasury|macro|yield|tariff/i.test(haystack)) return "macro";
  return "crypto";
}

export function newsByBucket(news, bucket) {
  const target = String(bucket || "").toLowerCase();
  return (news || []).filter((item) => inferNewsBucket(item) === target);
}

export function renderFleetReportHtml(state, fleet) {
  const fd = state.fleet_data?.[fleet] || {};
  const sys = fd.system || {};
  const ctx = (state.market_context || {})[fleet] || {};
  const keywords = FLEET_SYMBOL_KEYWORDS[fleet] || [fleet.toLowerCase()];
  const relatedNews = (state.news || [])
    .filter((item) => {
      const haystack = `${item.title || ""} ${item.summary || ""} ${(item.targets || []).join(" ")}`.toLowerCase();
      return keywords.some((word) => haystack.includes(word)) || (item.targets || []).includes(fleet);
    })
    .slice(0, 4);

  const newsBlock = relatedNews.length
    ? relatedNews
        .map(
          (item) => `
        <li style="margin-bottom:8px;">
          <b style="color:var(--cyan);font-size:11px;">${escapeHtml(normalizeText(item.category, "新聞"))}</b>
          <p style="margin:4px 0;font-size:12px;line-height:1.5;color:rgba(238,250,255,0.9);">
            ${escapeHtml(normalizeText(item.summary_zh || item.summary || item.title, ""))}
          </p>
        </li>`,
        )
        .join("")
    : `<li style="color:rgba(255,255,255,0.4);">目前沒有與 ${escapeHtml(fleet)} 直接相關的全球新聞。</li>`;

  return `
    <div style="display:grid;gap:10px;">
      <div class="station-stat-row"><dt>艦隊狀態</dt><dd>${escapeHtml(normalizeText(sys.status, "NORMAL"))}</dd></div>
      <div class="station-stat-row"><dt>最新訊號</dt><dd>${escapeHtml(normalizeText(sys.last_signal, "HOLD"))}</dd></div>
      <div class="station-stat-row"><dt>合約標的</dt><dd>${escapeHtml(normalizeText(ctx.symbol, "--"))}</dd></div>
      <div class="station-stat-row"><dt>資金費率</dt><dd>${(Number(ctx.funding_rate || 0) * 100).toFixed(4)}%</dd></div>
      <div class="station-stat-row"><dt>市場結構</dt><dd>${escapeHtml(normalizeText(ctx.market_regime, "normal"))}</dd></div>
      <p style="font-size:11px;color:rgba(255,255,255,0.45);margin:4px 0 0;">${escapeHtml(normalizeText(sys.last_reason, ""))}</p>
      <p class="station-sidebar-title" style="margin-top:8px;">${escapeHtml(fleet)} 相關全球新聞</p>
      <ul class="panel-list" style="padding-left:0;list-style:none;">${newsBlock}</ul>
    </div>
  `;
}
