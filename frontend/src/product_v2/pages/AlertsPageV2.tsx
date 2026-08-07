import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { WatchStarButton } from "../../components/WatchStarButton";
import { ANOMALY_TYPE_LABEL } from "../../market/anomalyTypes";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import { loadRankHistory } from "../../market/liveMarketRanking";

type AlertKind = "ranking" | "opportunity" | "risk" | "market" | "data" | "watchlist";

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

type FilterId = "ALL" | "RANKING" | "OPPORTUNITY" | "RISK" | "MARKET" | "DATA" | "WATCHLIST";

const READ_KEY = "nexus.alerts.read.v2";

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
  ranking: "排名",
  opportunity: "狀態",
  risk: "風險",
  market: "市場",
  data: "資料",
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

/** Product V2 Alerts — ranking / state / risk / data events. */
export function AlertsPageV2() {
  const anomalies = useMarketAnomalies();
  const { longs, shorts, events, status } = useMarketScannerOverview();
  const ranking = useLiveMarketRanking();
  const [filter, setFilter] = useState<FilterId>("ALL");
  const [readIds, setReadIds] = useState<Set<string>>(() => loadReadIds());

  const stream = useMemo(() => {
    const items: StreamItem[] = [];

    const hist = [...ranking.events, ...loadRankHistory()].slice(0, 40);
    const seen = new Set<string>();
    for (const e of hist) {
      if (seen.has(e.id)) continue;
      seen.add(e.id);
      items.push({
        id: `rank-${e.id}`,
        kind: "ranking",
        typeLabel: e.rank_event,
        what: `${e.symbol.replace("USDT", "")} · ${e.rank_event}${
          e.rank != null ? ` #${e.rank}` : ""
        }${e.previous_rank != null ? `（原 #${e.previous_rank}）` : ""}`,
        why: `${e.primary_reason} · ${e.market_change}`,
        asset: e.symbol.replace("USDT", ""),
        symbol: e.symbol,
        href: `/market/${e.symbol}`,
        time: agoLabel(e.timestamp),
        ts: e.timestamp,
      });
    }

    for (const a of anomalies) {
      if (a.status !== "NEW" && a.status !== "ACTIVE" && a.status !== "COOLING") continue;
      const type = String(a.type || "").toUpperCase();
      let kind: AlertKind = "market";
      if (type.includes("RISK") || type.includes("LIQ") || type.includes("OVER")) kind = "risk";
      else if (type.includes("FUND") || type.includes("OI") || type.includes("VOL")) kind = "market";
      else if (type.includes("DATA") || type.includes("STALE") || type.includes("QUALITY")) kind = "data";
      else if (type.includes("WATCH")) kind = "watchlist";
      else if (type.includes("OPP") || type.includes("CONFIRM") || type.includes("SIGNAL") || type.includes("STAGE"))
        kind = "opportunity";

      items.push({
        id: `anom-${a.id}`,
        kind,
        typeLabel: (ANOMALY_TYPE_LABEL as Record<string, string>)[a.type] || a.type || "異動",
        what: a.title || a.type || "市場異動",
        why: a.explanation || "掃描層偵測到需關注的變化",
        asset: a.symbol?.replace("USDT", "") || "—",
        symbol: a.symbol,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
        time: agoLabel(a.lastSeenAt ?? a.observedAt ?? null),
        ts: a.lastSeenAt ?? a.observedAt ?? Date.now(),
      });
    }

    for (const e of events) {
      const type = String(e.type || "").toUpperCase();
      const kind: AlertKind = type.includes("RANK")
        ? "ranking"
        : type.includes("STAGE")
          ? "opportunity"
          : type.includes("OVER")
            ? "risk"
            : "market";
      items.push({
        id: `evt-${e.id}`,
        kind,
        typeLabel: e.type || "事件",
        what: `${e.symbol.replace("USDT", "")} · ${e.type || "事件"}`,
        why: e.explanation || "掃描事件",
        asset: e.symbol.replace("USDT", ""),
        symbol: e.symbol,
        href: `/market/${e.symbol}`,
        time: agoLabel(e.timestamp ?? null),
        ts: e.timestamp ?? Date.now(),
      });
    }

    for (const c of [...longs, ...shorts].slice(0, 12)) {
      if (c.stage === "CONFIRMED" || c.stage === "OVEREXTENDED" || c.stage === "AWAITING_CONFIRMATION") {
        items.push({
          id: `cand-${c.id}`,
          kind: c.stage === "OVEREXTENDED" ? "risk" : "opportunity",
          typeLabel: c.stage,
          what: `${c.symbol.replace("USDT", "")} · ${c.stage}`,
          why: c.reasons?.[0] || "候選狀態變更",
          asset: c.symbol.replace("USDT", ""),
          symbol: c.symbol,
          href: `/market/${c.symbol}`,
          time: agoLabel(c.lastUpdatedAt),
          ts: c.lastUpdatedAt ?? Date.now(),
        });
      }
    }

    if (status?.lastError) {
      items.push({
        id: "data-error",
        kind: "data",
        typeLabel: "資料品質",
        what: "掃描服務異常",
        why: String(status.lastError),
        asset: "—",
        href: "/scanner",
        time: agoLabel(status.lastCycleAt),
        ts: status.lastCycleAt ?? Date.now(),
      });
    }

    const fresh = String(status?.freshness || "").toUpperCase();
    if (fresh.includes("STALE") || fresh.includes("DEGRAD") || fresh.includes("DELAY")) {
      items.push({
        id: "data-fresh",
        kind: "data",
        typeLabel: "資料品質",
        what: `資料 ${status?.freshness}`,
        why: "解讀應更保守",
        asset: "—",
        href: "/scanner",
        time: agoLabel(status?.lastCycleAt),
        ts: status?.lastCycleAt ?? Date.now(),
      });
    }

    items.sort((a, b) => b.ts - a.ts);
    return items.filter((m, i, arr) => arr.findIndex((x) => x.id === m.id) === i);
  }, [anomalies, events, longs, shorts, status, ranking.events]);

  const filtered = useMemo(() => {
    if (filter === "ALL") return stream;
    const map: Record<Exclude<FilterId, "ALL">, AlertKind> = {
      RANKING: "ranking",
      OPPORTUNITY: "opportunity",
      RISK: "risk",
      MARKET: "market",
      DATA: "data",
      WATCHLIST: "watchlist",
    };
    return stream.filter((s) => s.kind === map[filter]);
  }, [stream, filter]);

  const groups = useMemo(() => {
    const today: StreamItem[] = [];
    const yesterday: StreamItem[] = [];
    const earlier: StreamItem[] = [];
    for (const item of filtered) {
      const b = dayBucket(item.ts);
      if (b === "today") today.push(item);
      else if (b === "yesterday") yesterday.push(item);
      else earlier.push(item);
    }
    return [
      { id: "today", title: "今天", items: today },
      { id: "yesterday", title: "昨天", items: yesterday },
      { id: "earlier", title: "更早", items: earlier },
    ].filter((g) => g.items.length > 0);
  }, [filtered]);

  const markRead = (id: string) => {
    const next = new Set(readIds);
    next.add(id);
    setReadIds(next);
    saveReadIds(next);
  };

  const filters: { id: FilterId; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "RANKING", label: "排名" },
    { id: "OPPORTUNITY", label: "狀態" },
    { id: "RISK", label: "風險" },
    { id: "MARKET", label: "市場" },
    { id: "DATA", label: "資料" },
    { id: "WATCHLIST", label: "自選" },
  ];

  return (
    <div data-testid="product-v2-alerts" data-nexus-product-generation="2">
      <header>
        <h1 className="mp2-page-title">警報</h1>
        <p className="mp2-page-sub">排名 · 狀態 · 風險 · 資料</p>
      </header>

      <div className="mp2-chip-row" style={{ marginTop: 12 }} role="group" aria-label="警報篩選">
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            className={filter === f.id ? "active" : undefined}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <p className="muted" style={{ marginTop: 20 }}>
          目前沒有警報
        </p>
      ) : (
        groups.map((g) => (
          <section key={g.id} className="mp2-alert-day" aria-label={g.title}>
            <h2>{g.title}</h2>
            {g.items.map((item) => {
              const unread = !readIds.has(item.id);
              return (
                <article
                  key={item.id}
                  className={`mp2-alert-row${unread ? " unread" : ""}`}
                  onClick={() => markRead(item.id)}
                >
                  <span className="time">{item.time}</span>
                  <span className="kind">{KIND_LABEL[item.kind]}</span>
                  <div>
                    <Link to={item.href}>
                      <strong>{item.what}</strong>
                    </Link>
                    <div className="muted" style={{ fontSize: "0.8125rem", marginTop: 2 }}>
                      {item.why}
                    </div>
                    <div className="muted" style={{ fontSize: "0.75rem", marginTop: 2 }}>
                      {item.typeLabel} · {item.asset}
                    </div>
                  </div>
                  <div>{item.symbol ? <WatchStarButton symbol={item.symbol} /> : null}</div>
                </article>
              );
            })}
          </section>
        ))
      )}
    </div>
  );
}
