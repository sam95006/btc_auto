import { Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { loadEventPrefs, loadReadEventIds, type EventPrefs } from "../market/eventPrefs";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { fetchSectorsStatus } from "../market/sectorApi";
import { EventBellButton, EventCenterDrawer } from "./EventCenter";
import { SystemStatusDrawer } from "./SystemStatusDrawer";
import { UiDensityToggle } from "../member/UiDensityToggle";
import { mapMarketFreshnessDisplay } from "../market/dataTruthFreshness";

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 5) return "剛剛更新";
  if (sec < 60) return `${sec} 秒前更新`;
  return `${Math.round(sec / 60)} 分鐘前更新`;
}

/**
 * Compact global header — Founder funnel metric labels (discovery ≠ monitoring).
 */
export function MarketTopTicker() {
  const navigate = useNavigate();
  const { status, events } = useMarketScannerOverview();
  const [q, setQ] = useState("");
  const [eventOpen, setEventOpen] = useState(false);
  const [sysOpen, setSysOpen] = useState(false);
  const [prefs, setPrefs] = useState<EventPrefs>(() => loadEventPrefs());
  const [readTick, setReadTick] = useState(0);
  const [breadth, setBreadth] = useState<number | null>(null);
  const [nowTick, setNowTick] = useState(0);

  useEffect(() => {
    let alive = true;
    void fetchSectorsStatus()
      .then((s) => {
        if (alive && s.breadthMarketCount != null) setBreadth(s.breadthMarketCount);
      })
      .catch(() => undefined);
    const id = window.setInterval(() => {
      setNowTick((n) => n + 1);
      void fetchSectorsStatus()
        .then((s) => {
          if (alive && s.breadthMarketCount != null) setBreadth(s.breadthMarketCount);
        })
        .catch(() => undefined);
    }, 30000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowTick((n) => n + 1), 5000);
    return () => window.clearInterval(id);
  }, []);

  const unread = useMemo(() => {
    void readTick;
    const read = loadReadEventIds();
    return events.filter((e) => !read.has(e.id)).length;
  }, [events, readTick]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const sym = q.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!sym) return;
    const full = sym.endsWith("USDT") ? sym : `${sym}USDT`;
    navigate(`/market/${full}`);
    setQ("");
  };

  const freshDisp = mapMarketFreshnessDisplay(status?.freshness, {
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
    source: status?.source,
  });
  const deep = status?.symbolCount ?? "—";
  const updated = agoLabel(status?.lastCycleAt);
  void nowTick;

  return (
    <>
      <header className="market-top-ticker nx-topbar-p2 nx-topbar-p4" role="banner">
        <div className="mtt-left">
          <Link to="/overview" className="brand-mark mtt-brand">
            NEXUS
          </Link>
        </div>
        <div className="mtt-center nx-top-meta">
          <span
            className={`mtt-fresh-pill tone-${freshDisp.tone}`}
            title="市場資料新鮮度（不作全局 LIVE 過度宣稱）"
            data-testid="market-freshness-pill"
            data-freshness-raw={freshDisp.raw}
            data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
          >
            市場資料 {freshDisp.label}
          </span>
          <span
            className="mtt-meta-item"
            title="全市場發現：交易所／廣度列舉數（≠ 執行期驗證數）"
            data-testid="metric-discovery"
          >
            全市場發現 {breadth ?? "—"}
          </span>
          <span
            className="mtt-meta-item"
            title="即時監控：執行期深度追蹤池 symbolCount"
            data-testid="metric-monitoring"
          >
            即時監控 {deep}
          </span>
          <span className="mtt-meta-item muted" title="最後更新">
            {updated}
          </span>
          <span className="mtt-research-chip muted" title="執行狀態見系統狀態">
            研究模式 · 不執行交易
          </span>
        </div>
        <div className="mtt-right">
          <UiDensityToggle className="nx-topbar-density" />
          <form className="mtt-search" onSubmit={onSearch}>
            <label className="sr-only" htmlFor="mtt-q">
              搜尋標的
            </label>
            <input
              id="mtt-q"
              type="search"
              placeholder="BTC…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="搜尋標的"
            />
          </form>
          <EventBellButton
            unread={unread}
            onClick={() => {
              setEventOpen(true);
              setReadTick((n) => n + 1);
            }}
          />
          <button
            type="button"
            className="mtt-icon"
            title="系統狀態"
            aria-label="系統狀態"
            onClick={() => setSysOpen(true)}
          >
            ⚙
          </button>
          <button
            type="button"
            className="mtt-icon"
            title="NEX AI"
            aria-label="Open NEX AI"
            onClick={() => {
              document.querySelector<HTMLButtonElement>(".floating-ai-fab")?.click();
            }}
          >
            AI
          </button>
        </div>
      </header>
      <EventCenterDrawer
        open={eventOpen}
        onClose={() => {
          setEventOpen(false);
          setReadTick((n) => n + 1);
        }}
        events={events}
        onPrefsChange={setPrefs}
      />
      <SystemStatusDrawer open={sysOpen} onClose={() => setSysOpen(false)} />
      <span className="sr-only" data-toast={prefs.toast ? "1" : "0"} />
    </>
  );
}
