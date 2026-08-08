import { Link } from "react-router-dom";

/** Contextual upgrade only — never random FREE badges in market headers. */
export function ContextualUpgrade({
  title,
  detail,
  required = "PRO",
}: {
  title: string;
  detail: string;
  required?: "PRO" | "RESEARCH";
}) {
  return (
    <div className="mp2-upgrade-context" data-testid="contextual-upgrade" data-required={required}>
      <div>
        <strong>{title}</strong>
        <p className="muted">{detail}</p>
      </div>
      <Link to="/account" className="mp2-btn mp2-btn-ghost">
        升級至 {required}
      </Link>
    </div>
  );
}
