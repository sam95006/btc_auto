import { escapeHtml, normalizeText, translateImpact } from "../utils/presentation.js?v=20260510a";
import { getLayoutHotspots } from "../layout_state.js?v=20260503a";
import { newsByBucket } from "./station_hotspot_content.js?v=20260528a";

const NEWS_HOTSPOTS = [
  { id: "macro", label: "宏觀數據牆", x: 0.1, y: 0.22, w: 0.24, h: 0.3, section: "macro" },
  { id: "fed", label: "聯準會中樞", x: 0.4, y: 0.22, w: 0.22, h: 0.3, section: "fed" },
  { id: "crypto", label: "加密新聞牆", x: 0.67, y: 0.22, w: 0.24, h: 0.3, section: "crypto" },
  { id: "analyst_l", label: "新聞分析台", x: 0.18, y: 0.68, w: 0.2, h: 0.26, section: "discussion" },
  { id: "analyst_r", label: "重大情報區", x: 0.68, y: 0.68, w: 0.2, h: 0.26, section: "major" },
  { id: "ai_center", label: "AI 反思中心", x: 0.38, y: 0.6, w: 0.24, h: 0.26, section: "reflection" },
];

function textBody(item) {
  return normalizeText(item.summary_zh || item.summary || item.title_zh || item.title, "目前沒有可顯示的新聞摘要。");
}

function byBucket(news, bucket) {
  return newsByBucket(news, bucket);
}

function renderNewsFeedHtml(news, emptyText = "目前沒有資料。") {
  if (!news?.length) {
    return `<p style="color:rgba(255,255,255,0.4);font-size:12px;">${escapeHtml(emptyText)}</p>`;
  }
  return news.slice(0, 10).map((item) => `
    <div style="background:rgba(255,255,255,0.04);border-radius:10px;padding:12px 14px;margin-bottom:10px;border:1px solid rgba(79,216,255,0.12);">
      <b style="font-size:11px;color:var(--cyan);">${escapeHtml(normalizeText(item.category, "新聞分類"))} / ${escapeHtml(translateImpact(item.impact || "MEDIUM"))}</b>
      <p style="margin:6px 0 4px;font-size:13px;line-height:1.55;color:rgba(238,250,255,0.96);">${escapeHtml(textBody(item))}</p>
      <small style="display:block;color:rgba(255,255,255,0.55);font-size:11px;">${escapeHtml(item.time || "--")} / ${escapeHtml(item.source || "新聞來源")}</small>
    </div>
  `).join("");
}

function renderStationHtml(state) {
  const hotspots = getLayoutHotspots("NEWS", NEWS_HOTSPOTS);
  const hotspotHtml = hotspots.map((h) => `
    <button
      class="station-hotspot-btn"
      data-hotspot-id="${h.id}"
      data-sub-modal="${h.section}"
      data-sub-label="${h.label}"
      data-page="NEWS"
      style="left:${h.x * 100}%;top:${h.y * 100}%;width:${h.w * 100}%;height:${h.h * 100}%;"
      type="button"
    ><span>${h.label}</span></button>
  `).join("");

  return `
    <div class="station-page">
      <div class="station-main-area">
        <img class="station-main-img" src="/static/nexus/assets/news_nexus.png" alt="新聞站" />
        <div class="station-hotspot-layer">${hotspotHtml}</div>
      </div>
      <aside class="station-right-sidebar">
        ${buildRightSidebar(state)}
      </aside>
    </div>
  `;
}

function buildRightSidebar(state) {
  const news = state.news || [];
  const latestNews = news[0];
  const majorCount = news.filter((item) => item.impact === "HIGH").length;
  const macroCount = byBucket(news, "macro").length;
  const fedCount = byBucket(news, "fed").length;
  const cryptoCount = byBucket(news, "crypto").length;

  const latestHtml = latestNews
    ? `<div style="font-size:12px;line-height:1.65;color:rgba(238,250,255,0.86);">
        <b style="color:var(--cyan);display:block;margin-bottom:6px;">${escapeHtml(normalizeText(latestNews.category, "最新分類"))}</b>
        ${escapeHtml(textBody(latestNews))}
      </div>`
    : `<p style="color:rgba(255,255,255,0.4);font-size:12px;">目前沒有新的新聞摘要。</p>`;

  return `
    <p class="station-sidebar-title">新聞站摘要</p>
    <div class="station-stat-row"><dt>站點狀態</dt><dd>在線</dd></div>
    <div class="station-stat-row"><dt>新聞總數</dt><dd>${news.length} 則</dd></div>
    <div class="station-stat-row"><dt>重大情報</dt><dd>${majorCount} 則</dd></div>
    <div class="station-stat-row"><dt>宏觀數據</dt><dd>${macroCount} 則</dd></div>
    <div class="station-stat-row"><dt>聯準會 / 政策</dt><dd>${fedCount} 則</dd></div>
    <div class="station-stat-row"><dt>加密新聞</dt><dd>${cryptoCount} 則</dd></div>
    <p class="station-sidebar-title" style="margin-top:8px;">最新摘要</p>
    ${latestHtml}
  `;
}

export function getNewsModalContent(state, section) {
  const news = state.news || [];
  if (section === "macro") {
    return renderNewsFeedHtml(byBucket(news, "macro"), "目前沒有宏觀數據資料。");
  }
  if (section === "fed") {
    return renderNewsFeedHtml(byBucket(news, "fed"), "目前沒有聯準會或政策相關新聞。");
  }
  if (section === "crypto") {
    return renderNewsFeedHtml(byBucket(news, "crypto"), "目前沒有新的加密新聞。");
  }
  if (section === "major") {
    return renderNewsFeedHtml(news.filter((item) => item.impact === "HIGH"), "目前沒有重大情報。");
  }
  if (section === "discussion") {
    const macroHeadline = byBucket(news, "macro")[0];
    const fedHeadline = byBucket(news, "fed")[0];
    const cryptoHeadline = byBucket(news, "crypto")[0];
    const grouped = [
      `宏觀數據：${byBucket(news, "macro").length} 則${macroHeadline ? ` · ${textBody(macroHeadline).slice(0, 72)}` : ""}`,
      `聯準會 / 政策：${byBucket(news, "fed").length} 則${fedHeadline ? ` · ${textBody(fedHeadline).slice(0, 72)}` : ""}`,
      `加密新聞：${byBucket(news, "crypto").length} 則${cryptoHeadline ? ` · ${textBody(cryptoHeadline).slice(0, 72)}` : ""}`,
    ];
    return `
      <p style="color:rgba(255,255,255,0.45);font-size:11px;margin:0 0 8px;">全球 RSS 分類摘要（與雷達站市場掃描無關）</p>
      <ul class="panel-list">${grouped.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    `;
  }
  if (section === "reflection") {
    const briefing = state.station_briefings?.NEWS || {};
    const stationInstructions = Array.isArray(briefing.station_instructions) ? briefing.station_instructions : [];
    const riskNotes = Array.isArray(briefing.risk_notes) ? briefing.risk_notes : [];
    const watchlist = Array.isArray(briefing.watchlist) ? briefing.watchlist : [];
    const items = [...stationInstructions, ...watchlist, ...riskNotes];
    return items.length
      ? `<ul class="panel-list">${items.map((item) => `<li>${escapeHtml(normalizeText(item))}</li>`).join("")}</ul>`
      : `<p style="color:rgba(255,255,255,0.4);">目前沒有 AI 反思摘要。</p>`;
  }
  return `<p style="color:rgba(255,255,255,0.4);">目前沒有可顯示的新聞內容。</p>`;
}

export function buildNewsPage(state) {
  return {
    title: "新聞站",
    description: "集中分類宏觀數據、聯準會與加密新聞，供各站點判斷市場方向。",
    stationHtml: renderStationHtml(state),
  };
}
