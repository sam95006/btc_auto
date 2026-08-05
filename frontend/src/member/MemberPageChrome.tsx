import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useT, type MessageKey } from "../i18n";

export const MEMBER_LIVE_BANNER =
  "LIVE · lineage-bound · UNAVAILABLE never shown as 0 · STALE always indicated · no DEMO merge · local/staging";

export const MEMBER_DEMO_BANNER =
  "DEMO_DATA · fixture catalog · never Live · UNAVAILABLE never shown as 0 · AI suggestion ≠ filled order · no 60% guarantee";

/**
 * Member chrome: PUB2-J i18n title keys + honest mode chip.
 * chromeMode defaults to LIVE for live-bound pages; DEMO_DATA/replay must not claim LIVE.
 */
export function MemberPageChrome({
  titleKey,
  subtitleKey,
  title,
  subtitle,
  chromeMode = "LIVE",
  children,
}: {
  titleKey?: MessageKey;
  subtitleKey?: MessageKey;
  title?: string;
  subtitle?: string;
  chromeMode?: string;
  children: ReactNode;
}) {
  const t = useT();
  const resolvedTitle = titleKey ? t(titleKey) : title ?? "";
  const resolvedSubtitle = subtitleKey ? t(subtitleKey) : subtitle;
  const mode = (chromeMode || "LIVE").toUpperCase();
  const isLive = mode === "LIVE";
  const chipClass = isLive ? "member-chip member-chip-live" : "member-chip member-chip-demo";
  const banner = isLive ? MEMBER_LIVE_BANNER : MEMBER_DEMO_BANNER;

  return (
    <div className="page-stack member-page" data-chrome-mode={mode}>
      <header className="page-header member-page-header">
        <div className="member-title-row">
          <h1>{resolvedTitle}</h1>
          <span className={chipClass} role="status" data-chrome-label={mode}>
            {mode}
          </span>
        </div>
        {resolvedSubtitle ? <p className="page-sub">{resolvedSubtitle}</p> : null}
        <p
          className={
            isLive
              ? "member-demo-banner member-live-banner"
              : "member-demo-banner member-demo-data-banner"
          }
          role="status"
        >
          {banner}
        </p>
      </header>
      {children}
    </div>
  );
}

export function DecisionLink({ id, children }: { id: string; children?: ReactNode }) {
  return (
    <Link className="member-inline-link" to={`/decisions/${id}`}>
      {children ?? id}
    </Link>
  );
}

export function EmptyState({ label }: { label?: string }) {
  return (
    <div className="member-empty" role="status">
      <p>{label ?? "UNAVAILABLE"}</p>
      <p className="muted sm">Empty · UNAVAILABLE · no synthetic live values · no zero fill</p>
    </div>
  );
}
