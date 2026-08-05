import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export const MEMBER_LIVE_BANNER =
  "LIVE · lineage-bound · UNAVAILABLE never shown as 0 · STALE always indicated · no DEMO merge · local/staging";

export function MemberPageChrome({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="page-stack member-page">
      <header className="page-header member-page-header">
        <div className="member-title-row">
          <h1>{title}</h1>
          <span className="member-chip member-chip-live" role="status">
            LIVE
          </span>
        </div>
        {subtitle ? <p className="page-sub">{subtitle}</p> : null}
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

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="member-empty" role="status">
      <p>{label}</p>
      <p className="muted sm">Empty · UNAVAILABLE · no synthetic live values · no zero fill</p>
    </div>
  );
}
