import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MEMBER_DEMO_BANNER } from "./demoCatalog";

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
          <DemoDataBadge />
        </div>
        {subtitle ? <p className="page-sub">{subtitle}</p> : null}
        <p className="member-demo-banner" role="status">
          {MEMBER_DEMO_BANNER}
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
      <p className="muted sm">Empty state · DEMO catalog bound · no fabricated LIVE values</p>
    </div>
  );
}
