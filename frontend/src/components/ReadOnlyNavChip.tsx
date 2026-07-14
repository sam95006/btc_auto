import { Link } from "react-router-dom";

const HREF: Record<string, string> = {
  "View Evidence": "/evidence#doc-summaries",
  "Open Risk Card": "/risk-evidence",
  "Ask AI": "/overview#ai-copilot",
  "View Gate": "/overview#gate-checklist",
  "View Runbook": "/evidence#artifact-4-18-p2h-ops",
  "Generate Brief": "/overview#ai-copilot",
  "Add to Local Watch View": "/overview#candidate-board",
};

/** Read-only navigation chips — never Buy/Sell/Execute/Run. */
export function ReadOnlyNavChip({
  label,
}: {
  label:
    | "View Evidence"
    | "Open Risk Card"
    | "Ask AI"
    | "View Gate"
    | "View Runbook"
    | "Generate Brief"
    | "Add to Local Watch View";
}) {
  return (
    <Link className="ro-nav-chip" to={HREF[label] ?? "/overview"}>
      {label}
    </Link>
  );
}
