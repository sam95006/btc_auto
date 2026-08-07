import { NavLink, Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { usePublicEntitlements } from "../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../member/usePreviewReviewPlan";
import {
  ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1,
  MOBILE_BOTTOM_PRIMARY_V18_2_1,
  PRIMARY_ACTUAL_PANEL_NAV_V18_2_1,
  UTILITY_ACTUAL_PANEL_NAV_V18_2_1,
} from "../member/navigationContractV18_2_1";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { loadEventPrefs, loadReadEventIds, type EventPrefs } from "../market/eventPrefs";
import { EventBellButton, EventCenterDrawer } from "../components/EventCenter";
import { SystemStatusDrawer } from "../components/SystemStatusDrawer";

/** Desktop primary labels — Product V2 global top nav (Chinese). */
const PRIMARY_LABELS: Record<string, string> = {
  "/overview": "市場",
  "/opportunities": "機會",
  "/scanner": "掃描器",
  "/alerts": "警報",
  "/intelligence": "研究",
};

const MOBILE_SHORT: Record<string, string> = {
  "/overview": "總覽",
  "/opportunities": "機會",
  "/scanner": "掃描",
  "/alerts": "警報",
  "/intelligence": "研究",
  "/watchlist": "自選",
  "/assistant": "AI",
  "/account": "帳戶",
  "/organization": "組織",
};

export function ProductV2TopNav({ onOpenAi }: { onOpenAi: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const { events } = useMarketScannerOverview();
  const [eventOpen, setEventOpen] = useState(false);
  const [sysOpen, setSysOpen] = useState(false);
  const [prefs, setPrefs] = useState<EventPrefs>(() => loadEventPrefs());
  const [readTick, setReadTick] = useState(0);
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const showOrg = plan === "ENTERPRISE";

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

  return (
    <>
      <header className="mp2-topnav" role="banner" data-testid="mp2-topnav">
        <Link to="/overview" className="mp2-brand">
          NEXUS
        </Link>
        <nav className="mp2-primary-nav" aria-label="主選單">
          {PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              className={({ isActive }) => (isActive ? "is-active" : undefined)}
            >
              {PRIMARY_LABELS[i.to] || i.to}
            </NavLink>
          ))}
          {showOrg
            ? ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1.map((i) => (
                <NavLink
                  key={i.to}
                  to={i.to}
                  className={({ isActive }) => (isActive ? "is-active" : undefined)}
                >
                  組織
                </NavLink>
              ))
            : null}
        </nav>
        <div className="mp2-utility">
          <form className="mp2-search" onSubmit={onSearch}>
            <label className="sr-only" htmlFor="mp2-q">
              全域搜尋
            </label>
            <input
              id="mp2-q"
              type="search"
              placeholder="搜尋標的"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="全域搜尋"
            />
          </form>
          <NavLink to="/watchlist" className={({ isActive }) => (isActive ? "is-active" : undefined)}>
            自選
          </NavLink>
          <button type="button" className="mp2-util-btn" onClick={onOpenAi} aria-label="開啟 NEX AI 分析">
            分析
          </button>
          <span className="mp2-util-hide-sm">
            <EventBellButton
              unread={unread}
              onClick={() => setEventOpen(true)}
            />
          </span>
          <button
            type="button"
            className="mp2-util-btn mp2-util-hide-sm"
            onClick={() => setSysOpen(true)}
            aria-label="系統狀態"
          >
            狀態
          </button>
          <NavLink to="/account" className={({ isActive }) => (isActive ? "is-active" : undefined)}>
            帳戶
          </NavLink>
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

export function ProductV2MobileNav() {
  const primary = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    short: MOBILE_SHORT[i.to] || i.to,
  }));
  const mobilePaths = new Set<string>(MOBILE_BOTTOM_PRIMARY_V18_2_1);
  const bottom = primary.filter((p) => mobilePaths.has(p.to));
  const moreItems = [
    ...primary.filter((p) => !mobilePaths.has(p.to)),
    ...UTILITY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
      to: i.to,
      short: MOBILE_SHORT[i.to] || i.to,
    })),
  ];

  return (
    <nav className="mp2-mobile-nav" aria-label="行動導覽" data-testid="mp2-mobile-nav">
      {bottom.map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "is-active" : undefined)}>
          {l.short}
        </NavLink>
      ))}
      <details className="mp2-mobile-more">
        <summary>更多</summary>
        <div className="mp2-mobile-more-panel">
          {moreItems.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.short}
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}

/** Keep EventBell unused-deps quiet when events empty on first paint. */
export function useProductV2NavTick() {
  useEffect(() => undefined, []);
}
