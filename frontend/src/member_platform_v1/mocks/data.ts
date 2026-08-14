import type {
  AlertDto,
  AssetDetailDto,
  DashboardDto,
  MarketOverviewDto,
  MarketRankingRowDto,
  MembershipStatusDto,
  MembershipTier,
  PlanDto,
  RiskLevel,
} from "../types/dto";
import { ADVICE_LABELS, BIAS_LABELS, RISK_LABELS, TIER_LABELS } from "../lib/entitlements";

function spark(seed: number, n = 24): number[] {
  const out: number[] = [];
  let v = seed;
  for (let i = 0; i < n; i++) {
    v = v * (1 + ((i % 5) - 2) * 0.004 + (i % 3 === 0 ? 0.01 : -0.003));
    out.push(Number(v.toFixed(4)));
  }
  return out;
}

function candles(seed: number, n = 48) {
  const out: Array<{ o: number; h: number; l: number; c: number }> = [];
  let c = seed;
  for (let i = 0; i < n; i++) {
    const o = c;
    const drift = ((i % 7) - 3) * 0.0025 + (i % 4 === 0 ? 0.008 : -0.003);
    c = o * (1 + drift);
    const h = Math.max(o, c) * (1 + 0.004 + (i % 5) * 0.001);
    const l = Math.min(o, c) * (1 - 0.004 - (i % 3) * 0.001);
    out.push({ o, h, l, c });
  }
  return out;
}

function riskOf(level: RiskLevel) {
  return { risk: level, riskLabel: RISK_LABELS[level] };
}

export const MOCK_PLANS: PlanDto[] = [
  {
    id: "starter",
    name: "入門版",
    tagline: "先看懂方向",
    priceLabel: "NT$ 0 / 月",
    audience: "剛入門、想先搞清楚市場在做什麼的人",
    dailyValue: "每天打開就能看到市場方向、精選排行與今日白話重點",
    features: ["基礎市場總覽", "基礎排行", "觀察清單 10", "基礎提醒", "7 天歷史"],
  },
  {
    id: "advanced",
    name: "進階版",
    tagline: "完整觀察市場",
    priceLabel: "NT$ 299 / 月",
    audience: "想更完整追蹤機會與風險的投資人",
    dailyValue: "完整排行、進出場觀察、進階風險提醒與 90 天歷史",
    features: ["完整市場總覽", "多維度深度排行", "觀察清單 50", "進階提醒", "90 天歷史", "鏈上／情緒證據"],
  },
  {
    id: "professional",
    name: "專業版",
    tagline: "完整證據與即時提醒",
    priceLabel: "NT$ 799 / 月",
    audience: "積極交易與策略執行者",
    dailyValue: "即時風險、完整證據、自訂提醒、365 天回溯與有限 API",
    highlighted: true,
    features: ["進階版全部", "頂級資訊深度", "觀察清單 200", "自訂提醒策略", "365 天歷史", "有限 API", "Bridge 匯出"],
  },
  {
    id: "enterprise",
    name: "企業版",
    tagline: "團隊與機構",
    priceLabel: "聯絡我們",
    audience: "研究團隊、家族辦公室與機構需求",
    dailyValue: "專業版全部能力 + 高額度 API、Team/SSO 與專屬成功團隊",
    features: ["專業版全部", "觀察／歷史無上限", "高額度 API", "Bridge 完整匯出", "Team / SSO", "專屬成功團隊"],
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
    ...riskOf("medium"),
    sparkline: spark(3420),
    lastChangeLabel: "12 分鐘前狀態上調",
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
    ...riskOf("medium"),
    sparkline: spark(38),
    lastChangeLabel: "35 分鐘前進入可留意",
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
    ...riskOf("high"),
    sparkline: spark(168),
    lastChangeLabel: "28 分鐘前風險上調",
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
    ...riskOf("low"),
    sparkline: spark(612),
    lastChangeLabel: "2 小時前",
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
    ...riskOf("high"),
    sparkline: spark(0.148),
    lastChangeLabel: "1 小時前",
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
    beginnerReason: "方向還不夠明確，先等結構",
    ...riskOf("medium"),
    sparkline: spark(68450),
    lastChangeLabel: "今天維持觀察",
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
    ...riskOf("low"),
    sparkline: spark(0.72),
    lastChangeLabel: "昨天",
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
    ...riskOf("medium"),
    sparkline: spark(0.62),
    lastChangeLabel: "4 小時前轉弱",
  },
];

export const MOCK_OVERVIEW: MarketOverviewDto = {
  bias: "bullish",
  biasLabel: "偏多",
  advice: "observing",
  adviceLabel: "優先觀察",
  risk: "medium",
  riskLabel: "中等",
  biasDetail: "多方目前稍佔優勢",
  actionDetail: "避免追價，先鎖定少數標的",
  riskDetail: "短線波動增加",
  summary: "多數大型幣偏多，但追價風險不低，適合先鎖定少數標的觀察。",
  updatedAt: new Date().toISOString(),
};

export const MOCK_ALERTS: AlertDto[] = [
  {
    id: "a1",
    symbol: "SOLUSDT",
    title: "SOL 風險上調",
    body: "短線波動升高，若追高，回撤空間可能變大。建議先觀察，不要急著加碼。",
    severity: "high",
    category: "priority",
    timeLabel: "28 分鐘前",
    read: false,
  },
  {
    id: "a2",
    symbol: "ETHUSDT",
    title: "ETH 狀態：觀察中 → 可留意",
    body: "買盤與結構同步轉強，分數升至 84。仍需留意追價風險。",
    severity: "info",
    category: "watchlist",
    timeLabel: "12 分鐘前",
    read: false,
  },
  {
    id: "a3",
    symbol: "BTCUSDT",
    title: "BTC 方向仍不明確",
    body: "價格在區間整理，大盤方向尚未完全打開。",
    severity: "caution",
    category: "market",
    timeLabel: "1 小時前",
    read: false,
  },
  {
    id: "a4",
    title: "大額資金流向異常",
    body: "部分大型幣出現異常資金流動，請提高對主流幣的觀察頻率。",
    severity: "high",
    category: "risk",
    timeLabel: "3 小時前",
    read: false,
  },
  {
    id: "a5",
    symbol: "DOGEUSDT",
    title: "情緒幣波動過熱",
    body: "短線漲幅偏快，回落風險升高，先不要跟風追高。",
    severity: "caution",
    category: "risk",
    timeLabel: "5 小時前",
    read: true,
  },
  {
    id: "a6",
    symbol: "AVAXUSDT",
    title: "AVAX 進入可留意",
    body: "動能與資金關注同步上升，適合加入觀察清單追蹤。",
    severity: "info",
    category: "market",
    timeLabel: "6 小時前",
    read: true,
  },
];

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
      { id: "s1", timeLabel: "今天 14:20", summary: "觀察中 → 可留意" },
      { id: "s2", timeLabel: "昨天 09:10", summary: "偏多強度上升" },
      { id: "s3", timeLabel: "前天 18:40", summary: "風險維持中等" },
    ],
  },
};

export function getAssetDetail(symbol: string): AssetDetailDto | null {
  const row = MOCK_RANKING.find((r) => r.symbol === symbol.toUpperCase() || r.symbol === `${symbol.toUpperCase()}USDT`);
  const resolved =
    row ||
    MOCK_RANKING.find((r) => r.symbol.replace("USDT", "") === symbol.toUpperCase().replace("USDT", ""));
  if (!resolved) return null;
  const extra = DETAIL_EXTRA[resolved.symbol] || {
    whyInteresting: [resolved.beginnerReason, "目前仍在可追蹤名單內"],
    risks: [resolved.riskNote || "市場可能快速變化，請持續留意風險"],
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
    signalHistory: [{ id: "h1", timeLabel: "今天", summary: resolved.adviceLabel }],
  };
  return {
    ...resolved,
    sparkline: spark(resolved.price, 40),
    candles: candles(resolved.price),
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
  const limit = tier === "starter" ? 4 : 8;
  return {
    overview: MOCK_OVERVIEW,
    topAssets: MOCK_RANKING.slice(0, limit),
    highlights: [
      {
        id: "h1",
        title: "今天市場正在發生什麼",
        body: "大型幣整體偏多，ETH 與 AVAX 動能較強，BTC 仍在整理。",
        tone: "info",
      },
      {
        id: "h2",
        title: "為什麼市場轉強",
        body: "買盤回溫、短線結構修復，資金較集中在少數相對強勢幣。",
        tone: "positive",
      },
      {
        id: "h3",
        title: "今天先不要做什麼",
        body: "不要追已經大漲且風險偏高的標的，尤其是情緒驅動幣。",
        tone: "caution",
      },
      {
        id: "h4",
        title: "最需要注意的風險",
        body: "短線波動上升，若大盤突然轉弱，連動回檔機率會升高。",
        tone: "caution",
      },
    ],
    riskAlerts: MOCK_ALERTS.filter((a) => !a.read).slice(0, 4),
    watchlistPreview: MOCK_RANKING.filter((r) => watchSymbols.includes(r.symbol)).slice(0, 5),
    membership: membershipStatus(tier),
    signalChanges: [
      { id: "sc1", symbol: "ETHUSDT", fromLabel: "觀察中", toLabel: "可留意", timeLabel: "12 分鐘前" },
      { id: "sc2", symbol: "SOLUSDT", fromLabel: "風險中", toLabel: "高", timeLabel: "28 分鐘前" },
      { id: "sc3", symbol: "AVAXUSDT", fromLabel: "整理", toLabel: "可留意", timeLabel: "35 分鐘前" },
    ],
    plainLanguage: {
      happening: "大型幣整體偏多，資金集中在少數相對強勢標的。",
      whyStrong: "買盤回溫、短線結構修復，ETH 相對表現突出。",
      avoid: "不要追高波動、已大漲且風險偏高的幣。",
      topRisk: "短線波動上升，大盤若轉弱可能連動回檔。",
    },
    pulse: {
      marketCapLabel: "$2.41T",
      breadthBullPct: 62,
      breadthBearPct: 24,
      tickers: [
        { symbol: "BTC", price: 68450, change24hPct: 0.4 },
        { symbol: "ETH", price: 3420.5, change24hPct: 2.8 },
        { symbol: "SOL", price: 168.2, change24hPct: 4.1 },
      ],
      trend: [2.05, 2.08, 2.12, 2.09, 2.15, 2.18, 2.22, 2.2, 2.28, 2.31, 2.35, 2.41],
    },
  };
}
