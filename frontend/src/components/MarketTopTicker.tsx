import { Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { loadEventPrefs, loadReadEventIds, type EventPrefs } from "../market/eventPrefs";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { fetchSectorsStatus } from "../market/sectorApi";
import { EventBellButton, EventCenterDrawer } from "./EventCenter";
import { SystemStatusDrawer } from "./SystemStatusDrawer";
import { mapMarketFreshnessDisplay } from "../market/dataTruthFreshness";
import { deriveRegime } from "../market/marketSummary";

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 5) return "剛剛";
  if (sec < 60) return `${sec}s`;
  return `${Math.round(sec / 60)}m`;
}

/**
 * V18.2.9 top command bar — NEXUS | search | market state | notifications | NEX AI | account.
 * Density toggles live in Account display settings only (no mode-first UX).
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
  const pulse = {
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    breadth: status?.breadth,
    symbolCount: status?.symbolCount,
    freshness: status?.freshness,
  };
  const regime = deriveRegime(pulse);
  const deep = status?.symbolCount ?? "—";
  const updated = agoLabel(status?.lastCycleAt);
  void nowTick;

  return (
    <>
      <header className="nx10-cmd" role="banner" data-testid="nx10-cmd" data-product-gen="v18_2_10">
        <div className="nx10-cmd-left">
          <Link to="/overview" className="nx10-logo">
            NEXUS
          </Link>
          <form className="nx10-search" onSubmit={onSearch}>
            <label className="sr-only" htmlFor="nx10-q">
              全域搜尋標的
            </label>
            <input
              id="nx10-q"
              type="search"
              placeholder="搜尋標的…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="搜尋標的"
            />
          </form>
        </div>

        <div className="nx10-cmd-center" aria-label="市場與掃描狀態">
          <span className="nx10-chip nx10-chip" title="市場狀態">
            {regime}
          </span>
          <span
            className={`nx10-chip tone-${freshDisp.tone}`}
            title="市場資料新鮮度"
            data-testid="market-freshness-pill"
            data-freshness-raw={freshDisp.raw}
            data-global-live-overclaim={freshDisp.global_live_overclaim ? "1" : "0"}
          >
            {freshDisp.label}
          </span>
          <span
            className="nx10-meta"
            title="全市場發現 ≠ 即時監控"
            data-testid="metric-discovery"
          >
            發現 {breadth ?? "—"}
          </span>
          <span
            className="nx10-meta"
            title="執行期深度追蹤池"
            data-testid="metric-monitoring"
          >
            監控 {deep}
          </span>
          <span className="nx10-meta muted" title="掃描更新">
            掃描 {updated}
          </span>
        </div>

        <div className="nx10-cmd-right">
          <EventBellButton
            unread={unread}
            onClick={() => {
              setEventOpen(true);
              setReadTick((n) => n + 1);
            }}
          />
          <button
            type="button"
            className="nx10-icon-btn"
            title="系統狀態"
            aria-label="系統狀態"
            onClick={() => setSysOpen(true)}
          >
            ⚙
          </button>
          <button
            type="button"
            className="nx10-icon-btn"
            title="NEX AI"
            aria-label="Open NEX AI"
            onClick={() => {
              document.querySelector<HTMLButtonElement>(".nx10-ai-fab")?.click();
            }}
          >
            AI
          </button>
          <Link to="/account" className="nx10-account-link" title="帳戶">
            帳戶
          </Link>
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
