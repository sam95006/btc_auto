/**
 * Intelligence feed — backend-computed public-safe events from the realtime
 * context (SSE transitions + polled observations). NO fabricated sample events;
 * safe NEXUS semantics (no execution, no private trading).
 */
import { useEventsFeed } from "../../context/MarketContext";
import { useLocale } from "../../i18n";
import { fmtTime } from "../../lib/format";
import type { IntelEvent } from "../../types";

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
  const feed = useEventsFeed();
  const { t } = useLocale();
  if (feed === null) return <div className="corp-fs-feed"><div className="corp-fs-feed-empty" role="status">{t("st_loading")}</div></div>;
  if (feed.availability !== "READY") return <div className="corp-fs-feed"><div className="corp-fs-feed-empty corp-fs-unavail">{t("st_unavailable")}</div></div>;
  const rows = [...(feed.transitions || []), ...(feed.observations || [])].slice(0, 8);
  return (
    <div className="corp-fs-feed" data-testid="intelligence-feed">
      {rows.length ? rows.map((e, i) => <Row key={i} e={e} />) : <div className="corp-fs-feed-empty">{t("feed_empty")}</div>}
    </div>
  );
}
