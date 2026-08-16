import { chromium } from "playwright";

const base = process.env.NEXUS_MEMBER_URL || "https://nexus-member-preview-v18-2-1.zeabur.app";
const routes = ["/", "/login", "/register", "/forgot-password", "/plans", "/app", "/app/markets", "/app/watchlist", "/app/alerts", "/app/market/BTC", "/app/market/ETH", "/app/market/SOL", "/app/membership", "/app/account"];
const browser = await chromium.launch({ headless: true });
const requests = [];
const errors = [];

try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    page.on("request", request => requests.push(request.url()));
    page.on("console", message => {
      if (message.type() === "error") errors.push(message.text());
    });
    for (const route of routes) {
      const response = await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
      if (response?.status() !== 200) throw new Error(`route_status:${viewport.width}:${route}:${response?.status()}`);
      if ((await page.content()).match(/NEXUS-AUTONOMY|WAITING_MARKET|candidate_count|ResearchAutonomyService/i)) {
        throw new Error(`runtime_marker:${route}`);
      }
    }
    for (const route of ["/app", "/app/market/BTC"]) {
      await page.goto(`${base}${route}`, { waitUntil: "networkidle", timeout: 60_000 });
      const hasTimeline = await page.locator('script[src*="tradingview.com/external-embedding/embed-widget-timeline.js"]').count();
      if (!hasTimeline) throw new Error(`tradingview_widget_missing:${route}`);
    }
    await page.close();
  }
  if (!requests.some(url => url.includes("nexus-api-staging.zeabur.app/api/v1/"))) {
    throw new Error("api_v1_network_missing");
  }
  if (requests.some(url => /\/api\/(?:nexus\/markets|market\/tickers)/.test(url))) {
    throw new Error("obsolete_same_origin_api_used");
  }
  if (!requests.some(url => url.includes("s3.tradingview.com/external-embedding/embed-widget-timeline.js"))) {
    throw new Error("tradingview_network_missing");
  }
  if (errors.length) throw new Error(`console_errors:${errors.join(" | ").slice(0, 400)}`);
  console.log("TRADINGVIEW_NEWS_PASS");
  console.log("FRONTEND_API_V1_NETWORK_BOUNDARY_PASS");
  console.log("FULL_SITE_REAL_DATA_BINDING_PASS");
} finally {
  await browser.close();
}
