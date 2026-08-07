import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { WatchStarButton } from "../components/WatchStarButton";
import { ANOMALY_TYPE_LABEL } from "../market/anomalyTypes";

type AlertKind = "opportunity" | "risk" | "market" | "data" | "watchlist";

type StreamItem = {
  id: string;
  kind: AlertKind;
  typeLabel: string;
  what: string;
  why: string;
  asset: string;
  symbol?: string;
  href: string;
  time: string;
  ts: number;
};

type FilterId = "ALL" | "OPPORTUNITY" | "RISK" | "MARKET" | "DATA" | "WATCHLIST";

const READ_KEY = "nexus.alerts.read.v1829";

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec} 秒前`;
  if (sec < 3600) return `${Math.round(sec / 60)} 分鐘前`;
  return `${Math.round(sec / 3600)} 小時前`;
}

function loadReadIds(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as string[];
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function saveReadIds(ids: Set<string>) {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify([...ids].slice(-200)));
  } catch {
    /* ignore */
  }
}

const KIND_LABEL: Record<AlertKind, string> = {
  opportunity: "機會",
  risk: "風險",
  market: "市場",
  data: "資料品質",
  watchlist: "自選",
};

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function dayBucket(ts: number): "today" | "yesterday" | "earlier" {
  const now = new Date();
  const today = startOfDay(now);
  const yesterday = today - 86400000;
  if (ts >= today) return "today";
  if (ts >= yesterday) return "yesterday";
  return "earlier";
}

/**
 * V18.2.10 — Alerts as continuous event timeline grouped Today / Yesterday.
 */
export function AlertsPage() {
  const anomalies = useMarketAnomalies();
  const { longs, shorts, events, status } = useMarketScannerOverview();
  const [filter, setFilter] = useState<FilterId>("ALL");
  const [readIds, setReadIds] = useState<Set<string>>(() => loadReadIds());

  const stream = useMemo(() => {
    const items: StreamItem[] = [];

    for (const a of anomalies) {
      if (a.status !== "NEW" && a.status !== "ACTIVE" && a.status !== "COOLING") continue;
      const type = String(a.type || "").toUpperCase();
      let kind: AlertKind = "market";
      if (type.includes("RISK") || type.includes("LIQ") || type.includes("OVER")) kind = "risk";
      else if (type.includes("FUND") || type.includes("OI") || type.includes("VOL")) kind = "market";
      else if (type.includes("DATA") || type.includes("STALE") || type.includes("QUALITY")) kind = "data";
      else if (type.includes("WATCH")) kind = "watchlist";
      else if (type.includes("OPP") || type.includes("CONFIRM") || type.includes("SIGNAL"))
        kind = "opportunity";

      items.push({
        id: `anom-${a.id}`,
        kind,
        typeLabel: ANOMALY_TYPE_LABEL[a.type] || a.type || "異動",
        what: a.title || ANOMALY_TYPE_LABEL[a.type] || a.type,
        why: a.explanation || "市場結構出現需關注的變化",
        asset: a.symbol?.replace("USDT", "") || "—",
        symbol: a.symbol,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
        time: agoLabel(a.lastSeenAt || a.observedAt),
        ts: a.lastSeenAt || a.observedAt || 0,
      });
    }

    for (const e of events) {
      const t = String(e.type || "").toUpperCase();
      const kind: AlertKind = t.includes("RISK")
        ? "risk"
        : t.includes("CONFIRM") || t.includes("OPP")
          ? "opportunity"
          : "market";
      items.push({
        id: `evt-${e.id}`,
        kind,
        typeLabel: e.type || "掃描事件",
        what: e.type || "掃描事件",
        why: e.explanation,
        asset: e.symbol.replace("USDT", ""),
        symbol: e.symbol,
        href: `/market/${e.symbol}`,
        time: agoLabel(e.timestamp),
        ts: e.timestamp || 0,
      });
    }

    for (const c of [...longs, ...shorts]) {
      if (!(c.riskScore >= 70 || c.stage === "OVEREXTENDED")) continue;
      items.push({
        id: `risk-${c.id}`,
        kind: "risk",
        typeLabel: "風險條件",
        what: "風險條件升溫",
        why:
          c.stage === "OVEREXTENDED"
            ? "目前風險條件未通過 — 標的過熱／延伸"
            : `風險分數 ${Math.round(c.riskScore)} · 建議優先觀察而非進場`,
        asset: c.symbol.replace("USDT", ""),
        symbol: c.symbol,
        href: `/market/${c.symbol}`,
        time: agoLabel(c.lastUpdatedAt),
        ts: c.lastUpdatedAt || 0,
      });
    }

    const fresh = String(status?.freshness || "").toUpperCase();
    if (
      fresh.includes("STALE") ||
      fresh.includes("DEGRAD") ||
      fresh.includes("DELAY") ||
      fresh.includes("PARTIAL")
    ) {
      items.push({
        id: "data-freshness",
        kind: "data",
        typeLabel: "資料品質",
        what: "資料品質需保守解讀",
        why: "部分即時或掃描品質下降，解讀應更保守",
        asset: "—",
        href: "/scanner",
        time: "剛才",
        ts: Date.now(),
      });
    }

    items.sort((a, b) => b.ts - a.ts);
    const seen = new Set<string>();
    return items.filter((it) => {
      const key = `${it.asset}|${it.what}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [anomalies, events, longs, shorts, status?.freshness]);

  const filtered = useMemo(() => {
    if (filter === "ALL") return stream;
    const map: Record<Exclude<FilterId, "ALL">, AlertKind> = {
      OPPORTUNITY: "opportunity",
      RISK: "risk",
      MARKET: "market",
      DATA: "data",
      WATCHLIST: "watchlist",
    };
    const want = map[filter];
    return stream.filter((s) => s.kind === want);
  }, [stream, filter]);

  const groups = useMemo(() => {
    const today: StreamItem[] = [];
    const yesterday: StreamItem[] = [];
    const earlier: StreamItem[] = [];
    for (const item of filtered) {
      const b = dayBucket(item.ts || Date.now());
      if (b === "today") today.push(item);
      else if (b === "yesterday") yesterday.push(item);
      else earlier.push(item);
    }
    return [
      { id: "today", label: "今天", items: today },
      { id: "yesterday", label: "昨天", items: yesterday },
      { id: "earlier", label: "更早", items: earlier },
    ].filter((g) => g.items.length > 0);
  }, [filtered]);

  const markRead = (id: string) => {
    setReadIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      saveReadIds(next);
      return next;
    });
  };

  const filters: { id: FilterId; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "OPPORTUNITY", label: "機會" },
    { id: "RISK", label: "風險" },
    { id: "MARKET", label: "市場" },
    { id: "DATA", label: "資料品質" },
    { id: "WATCHLIST", label: "自選" },
  ];

  const renderItem = (item: StreamItem) => {
    const isRead = readIds.has(item.id);
    return (
      <article
        key={item.id}
        className={`nx10-alert-item${isRead ? " is-read" : ""}`}
        data-kind={item.kind}
      >
        <div className="time mono">{item.time}</div>
        <div className="asset mono">
          {item.symbol ? <Link to={item.href}>{item.asset}</Link> : item.asset}
        </div>
        <div className="type">{KIND_LABEL[item.kind]}</div>
        <div className="meaning">
          <p className="what">{item.what}</p>
          <p className="why">{item.why}</p>
        </div>
        <div className="nx10-alert-actions">
          <Link to={item.href} className="nx10-btn nx10-btn-tertiary" onClick={() => markRead(item.id)}>
            查看
          </Link>
          <button
            type="button"
            className="nx10-btn nx10-btn-tertiary"
            onClick={() => markRead(item.id)}
            disabled={isRead}
          >
            {isRead ? "已讀" : "設為已讀"}
          </button>
          {item.symbol ? <WatchStarButton symbol={item.symbol} /> : null}
        </div>
      </article>
    );
  };

  return (
    <div className="nx10-alerts" data-testid="alerts-v1829" data-product-gen="v18_2_10">
      <header className="nx10-alerts-head">
        <div>
          <h1 className="nx10-page-title">警報</h1>
          <p className="nx10-page-sub" style={{ marginBottom: 0 }}>
            連續事件時間軸 · 今天／昨天分組 · 非卡片牆
          </p>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: "0.8125rem" }}>
          {filtered.length} 則
          {status?.highRiskCandidates != null ? ` · 高風險 ${status.highRiskCandidates}` : ""}
        </p>
      </header>

      <div className="nx10-alert-filters" role="tablist" aria-label="警報篩選">
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={`nx10-chip-btn${filter === f.id ? " active" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="nx10-empty">
          <strong>目前沒有新警報</strong>
          不會用假警報填空。可建立條件等待，或回到掃描器持續觀察。
          <div className="nx10-actions">
            <Link to="/scanner" className="nx10-btn nx10-btn-primary">
              掃描全市場
            </Link>
            <Link to="/watchlist" className="nx10-btn nx10-btn-secondary">
              查看觀察清單
            </Link>
          </div>
        </div>
      ) : (
        <div role="feed" aria-label="警報事件時間軸">
          {groups.map((g) => (
            <section key={g.id} className="nx10-day-group" aria-label={g.label}>
              <h2 className="nx10-day-label">{g.label}</h2>
              {g.items.map(renderItem)}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
