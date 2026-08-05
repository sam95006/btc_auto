import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useT, type MessageKey } from "../i18n";

export const MEMBER_LIVE_BANNER =
  "LIVE · lineage-bound · UNAVAILABLE never shown as 0 · STALE always indicated · no DEMO merge · local/staging";

/**
 * Member chrome: PUB2-J i18n title keys + PUB2-B LIVE lineage banner.
 * DemoDataBadge / MEMBER_DEMO_BANNER intentionally omitted — LIVE surface must not merge DEMO.
 */
export function MemberPageChrome({
  titleKey,
  subtitleKey,
  title,
  subtitle,
  children,
}: {
  titleKey?: MessageKey;
  subtitleKey?: MessageKey;
  title?: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const t = useT();
  const resolvedTitle = titleKey ? t(titleKey) : title ?? "";
  const resolvedSubtitle = subtitleKey ? t(subtitleKey) : subtitle;

  return (
    <div className="page-stack member-page">
      <header className="page-header member-page-header">
        <div className="member-title-row">
          <h1>{resolvedTitle}</h1>
          <span className="member-chip member-chip-live" role="status">
            LIVE
          </span>
        </div>
        {resolvedSubtitle ? <p className="page-sub">{resolvedSubtitle}</p> : null}
        <p className="member-demo-banner member-live-banner" role="status">
          {MEMBER_LIVE_BANNER}
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
