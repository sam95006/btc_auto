/**
 * Intelligence feed — backend-computed public-safe events. Shows real detected
 * transitions (persisted across polls) first, then current-state observations.
 * NO fabricated sample events; the source is /api/corporate/v1/events. Safe NEXUS
 * semantics (no execution, no private trading).
 */
import { useEffect, useState } from "react";
import { getEvents } from "../../api/client";
import { fmtTime } from "../../lib/format";
import type { EventsFeed, IntelEvent } from "../../types";

const SEV_CLASS: Record<string, string> = { high: "down", medium: "warn", info: "accent" };
const SEV_LABEL: Record<string, string> = { high: "HIGH", medium: "WATCH", info: "INFO" };

function Row({ e }: { e: IntelEvent }) {
  return (
    <div className="corp-fs-feed-row" data-testid="feed-row">
      <span className="time">{fmtTime(e.ts)}</span>
      <span className="sym">{e.symbol ?? "MKT"}</span>
      <span className="txt">{e.text}</span>
      <span className="sev"><span className={`corp-fs-badge ${SEV_CLASS[e.severity] || "accent"}`}>{SEV_LABEL[e.severity] || "INFO"}</span></span>
    </div>
  );
}

export function IntelligenceFeed() {
  const [feed, setFeed] = useState<EventsFeed | null | undefined>(undefined);
  useEffect(() => {
    let on = true;
    const load = () => getEvents().then((f) => on && setFeed(f)).catch(() => on && setFeed(null));
    load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 30000);
    return () => { on = false; window.clearInterval(t); };
  }, []);

  if (feed === undefined) return <div className="corp-fs-feed"><div className="corp-fs-feed-empty" role="status">載入情報事件…</div></div>;
  if (!feed || feed.availability !== "READY") {
    return <div className="corp-fs-feed"><div className="corp-fs-feed-empty corp-fs-unavail">情報事件暫不可用</div></div>;
  }
  const rows = [...(feed.transitions || []), ...(feed.observations || [])].slice(0, 8);
  return (
    <div className="corp-fs-feed" data-testid="intelligence-feed">
      {rows.length ? rows.map((e, i) => <Row key={i} e={e} />) : <div className="corp-fs-feed-empty">目前無事件</div>}
    </div>
  );
}
