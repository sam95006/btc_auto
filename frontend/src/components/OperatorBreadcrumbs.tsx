import { Link } from "react-router-dom";

export type Crumb = { label: string; to?: string };

/** Lightweight Operator Console breadcrumbs (read-only navigation). */
export function OperatorBreadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav className="operator-breadcrumbs" aria-label="Breadcrumb">
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} className="crumb">
          {i > 0 ? <span className="crumb-sep">›</span> : null}
          {c.to ? (
            <Link className="deep-link" to={c.to}>
              {c.label}
            </Link>
          ) : (
            <span className="crumb-current">{c.label}</span>
          )}
        </span>
      ))}
      <span className="muted crumb-note"> · READ ONLY · docs navigation</span>
    </nav>
  );
}
