import { Link, useNavigate } from "react-router-dom";
import { useMemo, useState, type FormEvent } from "react";
import { loadViewMode, saveViewMode, type ViewMode } from "../market/viewPrefs";
import { loadEventPrefs, loadReadEventIds, type EventPrefs } from "../market/eventPrefs";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { EventBellButton, EventCenterDrawer } from "./EventCenter";
import { SystemStatusDrawer } from "./SystemStatusDrawer";

/**
 * Phase 2 top bar — brand, scanner freshness, Simple/Advanced, events, AI.
 * HOLD / Stage 4.19 live in System Status drawer (not primary chrome).
 */
export function MarketTopTicker() {
  const navigate = useNavigate();
  const { status, events } = useMarketScannerOverview();
  const [q, setQ] = useState("");
  const [view, setView] = useState<ViewMode>(() => loadViewMode());
  const [eventOpen, setEventOpen] = useState(false);
  const [sysOpen, setSysOpen] = useState(false);
  const [prefs, setPrefs] = useState<EventPrefs>(() => loadEventPrefs());
  const [readTick, setReadTick] = useState(0);

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

  const toggleView = () => {
    const next: ViewMode = view === "simple" ? "advanced" : "simple";
    setView(next);
    saveViewMode(next);
    window.dispatchEvent(new CustomEvent("nexus-view-mode", { detail: next }));
  };

  const coverage = status?.symbolCount ?? "—";
  const fresh = status?.freshness || "—";
  const updated = status?.lastCycleAt
    ? new Date(status.lastCycleAt).toLocaleTimeString()
    : "—";
  const cadence = status?.snapshotIntervalSec ?? 20;

  return (
    <>
      <header className="market-top-ticker nx-topbar-p2" role="banner">
        <div className="mtt-left">
          <Link to="/overview" className="brand-mark mtt-brand">
            NEXUS
          </Link>
          <span className="mtt-tagline muted">市場情報</span>
        </div>
        <div className="mtt-center nx-top-meta">
          <span className={`mtt-fresh-pill tone-${String(fresh).toLowerCase()}`} title="Scanner freshness">
            {fresh}
          </span>
          <span className="mtt-meta-item" title="掃描覆蓋">
            {coverage} 市場
          </span>
          <span className="mtt-meta-item muted" title="最後掃描">
            更新 {updated}
          </span>
          <span className="mtt-meta-item muted desktop-only">
            候選約每 {cadence} 秒更新
          </span>
          <span className="mtt-research-chip" title="研究模式">
            即時市場資料 · 研究模式 · 不執行交易
          </span>
        </div>
        <div className="mtt-right">
          <button type="button" className="mtt-view-toggle" onClick={toggleView} title="Simple / Advanced">
            {view === "simple" ? "簡易" : "進階"}
          </button>
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
            title="AI Commander"
            aria-label="Open AI Commander"
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
      {/* prefs reserved for toast gate via custom event */}
      <span className="sr-only" data-toast={prefs.toast ? "1" : "0"} />
    </>
  );
}
