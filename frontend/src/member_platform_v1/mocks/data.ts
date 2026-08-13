import type {
  AlertDto,
  AssetDetailDto,
  DashboardDto,
  MarketOverviewDto,
  MarketRankingRowDto,
  MembershipStatusDto,
  MembershipTier,
  PlanDto,
} from "../types/dto";
import { ADVICE_LABELS, BIAS_LABELS, RISK_LABELS, TIER_LABELS } from "../lib/entitlements";

export const MOCK_PLANS: PlanDto[] = [
  {
    id: "starter",
    name: "入門版",
    tagline: "先看懂市場方向與重點幣",
    priceLabel: "免費體驗",
    features: ["市場總覽", "精選排行（有限）", "簡單狀態說明", "今日重點"],
  },
  {
    id: "advanced",
    name: "進階版",
    tagline: "完整排行、理由與風險提醒",
    priceLabel: "NT$ 990 / 月",
    highlighted: true,
    features: ["完整市場排行", "為什麼值得看", "觀察清單", "風險提醒"],
  },
  {
    id: "professional",
    name: "專業版",
    tagline: "更深的市場證據與衍生品資訊",
    priceLabel: "NT$ 2,490 / 月",
    features: ["支持與反證", "衍生品概況", "流動性", "訊號紀錄", "進階圖表資訊"],
  },
  {
    id: "enterprise",
    name: "企業版",
    tagline: "團隊協作與資料整合",
    priceLabel: "洽詢報價",
    features: ["團隊席位", "API 概念預覽", "資料匯出", "企業整合預留"],
  },
];

export const MOCK_RANKING: MarketRankingRowDto[] = [
  {
    symbol: "ETHUSDT",
    name: "Ethereum",
    price: 3420.5,
    change24hPct: 2.8,
    bias: "bullish",
    biasLabel: BIAS_LABELS.bullish,
    advice: "watch_closely",
    adviceLabel: ADVICE_LABELS.watch_closely,
    score: 84,
    beginnerReason: "買盤與短線趨勢正在轉強",
  },
  {
    symbol: "SOLUSDT",
    name: "Solana",
    price: 168.2,
    change24hPct: 4.1,
    bias: "bullish",
    biasLabel: BIAS_LABELS.bullish,
    advice: "observing",
    adviceLabel: ADVICE_LABELS.observing,
    score: 78,
    beginnerReason: "有機會，但目前追價風險偏高",
    riskNote: "波動較大，適合先觀察",
  },
  {
    symbol: "BTCUSDT",
    name: "Bitcoin",
    price: 68450,
    change24hPct: 0.4,
    bias: "neutral",
    biasLabel: BIAS_LABELS.neutral,
    advice: "wait",
    adviceLabel: ADVICE_LABELS.wait,
    score: 61,
    beginnerReason: "方向還不夠明確",
  },
  {
    symbol: "BNBUSDT",
    name: "BNB",
    price: 612.3,
    change24hPct: 1.2,
    bias: "bullish",
    biasLabel: BIAS_LABELS.bullish,
    advice: "observing",
    adviceLabel: ADVICE_LABELS.observing,
    score: 72,
    beginnerReason: "動能溫和轉強，仍需確認延續",
  },
  {
    symbol: "XRPUSDT",
    name: "XRP",
    price: 0.62,
    change24hPct: -1.5,
    bias: "bearish",
    biasLabel: BIAS_LABELS.bearish,
    advice: "wait",
    adviceLabel: ADVICE_LABELS.wait,
    score: 48,
    beginnerReason: "賣壓偏多，暫時不急著切入",
  },
  {
    symbol: "DOGEUSDT",
    name: "Dogecoin",
    price: 0.148,
    change24hPct: 6.2,
    bias: "bullish",
    biasLabel: BIAS_LABELS.bullish,
    advice: "observing",
    adviceLabel: ADVICE_LABELS.observing,
    score: 69,
    beginnerReason: "短線熱度高，但容易快速回落",
    riskNote: "情緒驅動明顯",
  },
  {
    symbol: "ADAUSDT",
    name: "Cardano",
    price: 0.72,
    change24hPct: -0.8,
    bias: "neutral",
    biasLabel: BIAS_LABELS.neutral,
    advice: "wait",
    adviceLabel: ADVICE_LABELS.wait,
    score: 55,
    beginnerReason: "整理中，尚無清楚方向",
  },
  {
    symbol: "AVAXUSDT",
    name: "Avalanche",
    price: 38.4,
    change24hPct: 3.3,
    bias: "bullish",
    biasLabel: BIAS_LABELS.bullish,
    advice: "watch_closely",
    adviceLabel: ADVICE_LABELS.watch_closely,
    score: 80,
    beginnerReason: "動能與資金關注同步上升",
  },
];

export const MOCK_OVERVIEW: MarketOverviewDto = {
  bias: "bullish",
  biasLabel: BIAS_LABELS.bullish,
  advice: "observing",
  adviceLabel: ADVICE_LABELS.observing,
  risk: "medium",
  riskLabel: RISK_LABELS.medium,
  summary: "多數大型幣偏多，但追價風險不低，適合先鎖定少數標的觀察。",
  updatedAt: new Date().toISOString(),
};

export const MOCK_ALERTS: AlertDto[] = [
  {
    id: "a1",
    symbol: "SOLUSDT",
    title: "追價風險升高",
    body: "短線漲幅偏快，若再追高，回撤空間可能變大。",
    severity: "caution",
    timeLabel: "12 分鐘前",
    read: false,
  },
  {
    id: "a2",
    symbol: "BTCUSDT",
    title: "方向仍不明確",
    body: "價格在區間整理，建議等待更清楚的方向訊號。",
    severity: "info",
    timeLabel: "1 小時前",
    read: false,
  },
  {
    id: "a3",
    title: "整體波動上升",
    body: "市場波動較平常略高，請降低一次看太多幣的負擔。",
    severity: "high",
    timeLabel: "3 小時前",
    read: true,
  },
];

function spark(seed: number): number[] {
  const out: number[] = [];
  let v = seed;
  for (let i = 0; i < 32; i++) {
    v = v * (1 + ((i % 5) - 2) * 0.004 + (i % 3 === 0 ? 0.01 : -0.003));
    out.push(Number(v.toFixed(2)));
  }
  return out;
}

const DETAIL_EXTRA: Record<string, Partial<AssetDetailDto>> = {
  ETHUSDT: {
    whyInteresting: [
      "短線買盤增加，價格結構偏多",
      "相對大盤表現較穩定",
      "市場關注度維持在高檔",
    ],
    risks: ["若大盤突然轉弱，連帶回檔機率升高", "短線已有一段漲幅，追價需更謹慎"],
    invalidation: ["跌破近期整理區間下緣", "買盤明顯縮量且跌勢擴大"],
    evidence: {
      supporting: ["短線動能轉強", "相對強勢仍在", "活躍度維持"],
      contradicting: ["部分獲利了結壓力出現", "資金費率略偏擁擠"],
    },
    derivatives: {
      fundingLabel: "略偏多",
      oiLabel: "持倉溫和上升",
      note: "衍生品情緒偏多，但尚未極端。",
    },
    liquidity: {
      spreadLabel: "價差正常",
      depthLabel: "深度充足",
      note: "流動性良好，適合一般觀察與進出參考。",
    },
    signalHistory: [
      { id: "s1", timeLabel: "今天 14:20", summary: "偏多強度上升" },
      { id: "s2", timeLabel: "昨天 09:10", summary: "從觀察中轉為可留意" },
    ],
  },
};

export function getAssetDetail(symbol: string): AssetDetailDto | null {
  const row = MOCK_RANKING.find((r) => r.symbol === symbol);
  if (!row) return null;
  const extra = DETAIL_EXTRA[symbol] || {
    whyInteresting: [row.beginnerReason, "目前仍在可追蹤名單內"],
    risks: [row.riskNote || "市場可能快速變化，請持續留意風險"],
    invalidation: ["方向判斷被明顯反向走勢打破", "風險等級快速升高"],
    evidence: {
      supporting: ["結構尚未破壞"],
      contradicting: ["仍需更多確認"],
    },
    derivatives: {
      fundingLabel: "中性偏多",
      oiLabel: "變化不大",
      note: "衍生品未出現極端訊號。",
    },
    liquidity: {
      spreadLabel: "正常",
      depthLabel: "尚可",
      note: "流動性足夠日常觀察。",
    },
    signalHistory: [{ id: "h1", timeLabel: "今天", summary: row.adviceLabel }],
  };
  return {
    ...row,
    sparkline: spark(row.price),
    whyInteresting: extra.whyInteresting!,
    risks: extra.risks!,
    invalidation: extra.invalidation!,
    evidence: extra.evidence,
    derivatives: extra.derivatives,
    liquidity: extra.liquidity,
    signalHistory: extra.signalHistory,
  };
}

export function membershipStatus(tier: MembershipTier): MembershipStatusDto {
  return {
    tier,
    tierName: TIER_LABELS[tier],
    renewLabel: tier === "starter" ? "目前為入門體驗" : "下次續期：30 天後（模擬）",
    seatsLabel: tier === "enterprise" ? "團隊席位：5（模擬）" : undefined,
  };
}

export function buildDashboard(tier: MembershipTier, watchSymbols: string[]): DashboardDto {
  const limit = tier === "starter" ? 3 : 6;
  return {
    overview: MOCK_OVERVIEW,
    topAssets: MOCK_RANKING.slice(0, limit),
    highlights: [
      {
        id: "h1",
        title: "大型幣偏多",
        body: "ETH、SOL 等標的動能較強，但仍需留意追價風險。",
        tone: "positive",
      },
      {
        id: "h2",
        title: "BTC 方向不明",
        body: "比特幣仍在整理，暫時不急著下結論。",
        tone: "info",
      },
      {
        id: "h3",
        title: "波動略升",
        body: "今日波動高於近幾日平均，建議縮小同時關注的數量。",
        tone: "caution",
      },
    ],
    riskAlerts: MOCK_ALERTS.filter((a) => !a.read).slice(0, 2),
    watchlistPreview: MOCK_RANKING.filter((r) => watchSymbols.includes(r.symbol)).slice(0, 4),
    membership: membershipStatus(tier),
  };
}
