export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function hasBrokenGlyphs(text) {
  const value = String(text ?? "").trim();
  if (!value) return true;
  if (/\?{3,}/.test(value)) return true;
  if (/[�]/.test(value)) return true;
  return false;
}

export function normalizeText(value, fallback = "目前沒有資料。") {
  const text = String(value ?? "").trim();
  if (!text || hasBrokenGlyphs(text)) return fallback;
  return text;
}

export function formatUnit(value, digits = 2) {
  return `${Number(value || 0).toFixed(digits)}U`;
}

const SIGNAL_LABELS = {
  BUY: "買進",
  SELL: "賣出",
  HOLD: "觀望",
  LONG: "做多",
  SHORT: "做空",
  REJECTED: "拒單",
};

const STATUS_LABELS = {
  ACTIVE: "啟用",
  NORMAL: "正常",
  DEFENSIVE: "防守",
  PAUSED: "暫停",
  MONITORING: "監控中",
  STANDBY: "待命中",
  OFFLINE: "離線",
  ONLINE: "在線",
  DISCONNECTED: "斷線",
  BLOCKED: "阻擋",
  ERROR: "錯誤",
  EXITED: "已離場",
  TRADING: "交易中",
  WORKER_OFFLINE: "工作節點離線",
};

const SEVERITY_LABELS = {
  NORMAL: "正常",
  WATCH: "關注",
  WARNING: "警示",
  ALERT_RED: "紅色警戒",
  RED: "紅色警戒",
};

const IMPACT_LABELS = {
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
};

const MEETING_TYPE_LABELS = {
  FIXED: "固定會議",
  EMERGENCY: "緊急會議",
  SCHEDULED_ROUND_TABLE: "固定圓桌會議",
  EMERGENCY_ROUND_TABLE: "緊急圓桌會議",
  NEWS_BRIEFING: "新聞簡報",
  state_updated: "狀態更新",
  meeting_created: "建立會議",
  trade_opened: "開倉",
  trade_closed: "平倉",
  order_rejected: "拒單",
  emergency_meeting_triggered: "觸發緊急會議",
};

const STATION_LABELS = {
  MAIN: "總站總覽",
  WORLD: "世界頻道",
  HQ: "HQ 總部",
  BTC: "BTC 艦隊",
  ETH: "ETH 艦隊",
  SOL: "SOL 艦隊",
  PEPE: "PEPE 艦隊",
  RADAR: "雷達站",
  NEWS: "新聞站",
  WHALE: "巨鯨監控",
  FUNDING: "資金費率",
  RISK: "風控中心",
  MARKET: "市場快照",
  LEDGER: "資金帳本",
};

const TRADE_EVENT_LABELS = {
  OPEN: "開倉",
  CLOSE: "平倉",
  TRADE: "交易",
  TRADE_OPENED: "開倉",
  TRADE_CLOSED: "平倉",
  LIVE: "即時持倉",
};

const REJECT_REASON_LABELS = {
  no_high_quality_context: "市場脈絡不足",
  adjusted_confidence_below_threshold: "信心分數低於門檻",
  funding_warning: "資金費率警示",
  similar_loss_pattern: "近期虧損模式相似",
  pepe_margin_above_btc_cap: "PEPE 保證金高於 BTC 限額",
  btc_eth_total_exposure_cap: "BTC / ETH 總曝險超限",
  market_context_blocked: "市場條件阻擋進場",
  quality_score_below_threshold: "品質分數不足",
  direction_cooldown_active: "方向冷卻中",
  strategy_regime_paused: "策略狀態暫停",
  fleet_paused_due_to_low_score: "艦隊分數過低暫停",
  btc_reverse_pressure: "BTC 反向壓力過高",
  high_volatility: "波動過高",
  low_volume: "成交量不足",
  poor_risk_reward: "風報比不足",
  memory_block: "歷史記憶阻擋",
  correlation_blocked: "相關性風險阻擋",
  risk_rejected: "風控拒絕",
  alert_level_blocks_entry: "警戒等級阻止進場",
  fleet_recent_win_rate_too_low: "近期勝率過低",
};

const REJECT_LAYER_LABELS = {
  market_context_filter: "市場脈絡過濾",
  signal_memory_engine: "訊號記憶引擎",
  confidence_calibrator: "信心校正",
  entry_quality_filter: "進場品質過濾",
  fleet_score_engine: "艦隊評分引擎",
  correlation_risk_engine: "相關性風險引擎",
  risk_control_engine: "風控引擎",
  meeting_memory_broadcaster: "會議記憶廣播器",
  signal_fusion_engine: "訊號融合引擎",
};

const WORLD_CAPTAIN_ROSTER = [
  "總部指揮官",
  "新聞站站長",
  "雷達站站長",
  "BTC 艦隊長",
  "ETH 艦隊長",
  "SOL 艦隊長",
  "PEPE 艦隊長",
];

const ROLE_ROSTERS = {
  HQ: ["總指揮官", "總部策略官", "總部風控官", "總部資金官"],
  BTC: ["BTC 艦隊長", "BTC 交易官", "BTC 風控官"],
  ETH: ["ETH 艦隊長", "ETH 交易官", "ETH 風控官"],
  SOL: ["SOL 艦隊長", "SOL 交易官", "SOL 風控官"],
  PEPE: ["PEPE 艦隊長", "PEPE 交易官", "PEPE 風控官"],
  RADAR: ["雷達站站長", "巨鯨監控官", "異常掃描官"],
  NEWS: ["新聞站站長", "宏觀分析官", "聯準會觀測官", "加密新聞官"],
  RISK: ["風控中心主任", "曝險評估官"],
  WHALE: ["巨鯨監控官"],
  FUNDING: ["資金費率分析官"],
  MARKET: ["市場快照分析官"],
  LEDGER: ["資金帳本管理官"],
};

const DEFAULT_TASKS = {
  HQ: "統整各站資訊，主持圓桌會議並下達總部決議。",
  BTC: "監控 BTC 趨勢與壓力區，準備交易與風險回報。",
  ETH: "評估 ETH 節奏與關鍵價位，維持交易節奏。",
  SOL: "追蹤 SOL 強弱切換與波段節奏。",
  PEPE: "監看高波動小幣情緒與風險敞口。",
  RADAR: "掃描巨鯨異動、異常波動與市場異常。",
  NEWS: "蒐集新聞、分類翻譯並產出重點摘要。",
  RISK: "檢查曝險、警報與停牌條件。",
  WHALE: "監控大額地址、資金流與異常移動。",
  FUNDING: "追蹤資金費率與多空擁擠度。",
  MARKET: "整理外部市場指數與開休市狀態。",
  LEDGER: "追蹤資金配置、借款與資產變化。",
};

export function translateSignal(value) {
  return SIGNAL_LABELS[String(value || "").toUpperCase()] || String(value || "觀望");
}

export function translateStatus(value) {
  return STATUS_LABELS[String(value || "").toUpperCase()] || String(value || "--");
}

export function translateSeverity(value) {
  return SEVERITY_LABELS[String(value || "").toUpperCase()] || String(value || "--");
}

export function translateImpact(value) {
  return IMPACT_LABELS[String(value || "").toUpperCase()] || String(value || "--");
}

export function translateMeetingType(value) {
  return MEETING_TYPE_LABELS[String(value || "")] || String(value || "會議");
}

export function translateStation(value) {
  const key = String(value || "").toUpperCase();
  return STATION_LABELS[key] || String(value || "--");
}

export function translateTradeEvent(value) {
  return TRADE_EVENT_LABELS[String(value || "").toUpperCase()] || normalizeText(value, "交易");
}

export function translateRejectReason(value) {
  return REJECT_REASON_LABELS[String(value || "")] || normalizeText(value, "未知拒單原因");
}

export function translateRejectLayer(value) {
  return REJECT_LAYER_LABELS[String(value || "")] || normalizeText(value, "未知檢查層");
}

export function buildRejectNarration(layer, reason) {
  return `${translateRejectLayer(layer)}：${translateRejectReason(reason)}`;
}

export function getLatestMeeting(state) {
  const meetings = Array.isArray(state?.meetings) ? state.meetings : [];
  return meetings[0] || null;
}

export function getRoleRoster(station) {
  const key = String(station || "").toUpperCase();
  if (key === "WORLD") return [...WORLD_CAPTAIN_ROSTER];
  return [...(ROLE_ROSTERS[key] || [])];
}

export function buildStationConversation(state, station) {
  const stationKey = String(station || "").toUpperCase();
  const channelRows = Array.isArray(state?.station_chats?.[stationKey]) ? [...state.station_chats[stationKey]] : [];

  if (stationKey === "WORLD") {
    return channelRows
      .map((item) => ({
        timestamp: item.timestamp || "--",
        station: "WORLD",
        speaker: normalizeText(item.speaker, "站長"),
        message: normalizeText(item.message, "目前沒有新的通訊內容。"),
        source: normalizeText(item.source, "世界頻道"),
        importance: normalizeText(item.importance, "INFO"),
      }))
      .sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)))
      .slice(-120);
  }

  const rows = [...channelRows];
  const latestMeeting = getLatestMeeting(state);
  const reports = Array.isArray(latestMeeting?.unit_reports?.[stationKey]) ? latestMeeting.unit_reports[stationKey] : [];
  for (const item of reports) {
    const fp = `${item.speaker}|${item.message}`;
    if (rows.some((row) => `${row.speaker}|${row.message}` === fp)) continue;
    rows.push({
      timestamp: latestMeeting?.time || "--",
      station: stationKey,
      speaker: normalizeText(item.speaker, `${translateStation(stationKey)} 單位`),
      message: normalizeText(item.message, "目前沒有新的單位報告。"),
      source: "會議報告",
      importance: "INFO",
    });
  }

  return rows
    .map((item) => ({
      timestamp: item.timestamp || "--",
      station: stationKey,
      speaker: normalizeText(item.speaker, `${translateStation(stationKey)} 單位`),
      message: normalizeText(item.message, "目前沒有新的通訊內容。"),
      source: normalizeText(item.source, translateStation(stationKey)),
      importance: normalizeText(item.importance, "INFO"),
    }))
    .sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)));
}

export function buildRoleWindows(state, station) {
  const stationKey = String(station || "").toUpperCase();
  const roster = getRoleRoster(stationKey);
  const rows = buildStationConversation(state, stationKey).slice(-8);

  return roster.map((role, index) => {
    const latestSpeech = rows[index]?.message || rows[rows.length - 1]?.message || "目前沒有新的回報。";
    return {
      role,
      currentTask: DEFAULT_TASKS[stationKey] || "持續監控並等待下一步指令。",
      latestSpeech: normalizeText(latestSpeech, "目前沒有新的回報。"),
      discussion: rows.slice(Math.max(0, rows.length - 3)).map((row) => row.message),
    };
  });
}
