import { chromium } from "playwright";

const base = process.env.NEXUS_MEMBER_URL || "https://nexus-member-preview-v18-2-1.zeabur.app";
const api = process.env.NEXUS_API_URL || "https://nexus-api-staging.zeabur.app";
const email = process.env.NEXUS_STAGING_SEED_EMAIL || "";
const password = process.env.NEXUS_STAGING_SEED_PASSWORD || "";
const routes = ["/", "/login", "/register", "/forgot-password", "/plans", "/app", "/app/markets", "/app/watchlist", "/app/alerts", "/app/market/BTC", "/app/market/ETH", "/app/market/SOL", "/app/membership", "/app/account"];
const browser = await chromium.launch({ headless: true });
const requests = [];
const errors = [];

try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    page.on("request", request => requests.push(request.url()));
    if (!email || !password) throw new Error("staging_seed_credentials_missing");
    await page.goto(`${base}/login`, { waitUntil: "domcontentloaded", timeout: 45_000 });
    const loginStatus = await page.evaluate(async ({ api, email, password }) => {
      const response = await fetch(`${api}/api/v1/member/session/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      return response.status;
    }, { api, email, password });
    if (loginStatus !== 200) throw new Error(`browser_seed_login:${loginStatus}`);
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
      await page.waitForTimeout(2_000);
      const widget = page.locator('[data-classification="LIVE_TRADINGVIEW"]');
      if (!await widget.count()) throw new Error(`tradingview_widget_missing:${route}`);
      if (!await widget.locator('a[href*="tradingview.com/news"]').count()) {
        throw new Error(`tradingview_news_link_missing:${route}`);
      }
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
