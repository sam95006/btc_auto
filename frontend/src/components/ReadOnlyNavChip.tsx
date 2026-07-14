import { Link } from "react-router-dom";

const DEFAULT_HREF: Record<string, string> = {
  "View Evidence": "/evidence#doc-summaries",
  "Open Risk Card": "/risk-evidence#checklist-safety-invariants",
  "Ask AI": "/overview#ai-copilot",
  "View Gate": "/overview#gate-checklist",
  "View Runbook": "/evidence#artifact-4-18-p2h-ops",
  "Generate Brief": "/overview#ai-copilot",
  "Add to Local Watch View": "/overview#candidate-board",
  "View Provider History": "/provider-shadow#provider-history-chart",
};

export type ReadOnlyNavLabel =
  | "View Evidence"
  | "Open Risk Card"
  | "Ask AI"
  | "View Gate"
  | "View Runbook"
  | "Generate Brief"
  | "Add to Local Watch View"
  | "View Provider History"
  | "Evidence"
  | "Gate"
  | "Provider"
  | "Risk";

const SHORT_DEFAULT: Partial<Record<ReadOnlyNavLabel, string>> = {
  Evidence: "/evidence#doc-summaries",
  Gate: "/overview#gate-checklist",
  Provider: "/provider-shadow#provider-history-chart",
  Risk: "/risk-evidence#checklist-safety-invariants",
};

/** Read-only navigation chips — never Buy/Sell/Execute/Run. */
export function ReadOnlyNavChip({
  label,
  to,
}: {
  label: ReadOnlyNavLabel;
  to?: string;
}) {
  const href =
    to ?? DEFAULT_HREF[label] ?? SHORT_DEFAULT[label] ?? "/overview";
  return (
    <Link className="ro-nav-chip" to={href}>
      {label}
    </Link>
  );
}
