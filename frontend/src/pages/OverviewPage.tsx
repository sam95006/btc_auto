import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { SimplifiedMarketDashboard } from "../components/SimplifiedMarketDashboard";
import {
  ETH_WATCH_REAPPEARANCE_CHECKLIST,
  SHORT_REGRESSION_CHECKLIST,
  STAGE_419_DOSSIER_CHECKLIST,
} from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";

/**
 * MVP-22 market dashboard home — boards first, gate docs behind optional reveal.
 */
export function OverviewPage() {
  useHashScroll();
  const loc = useLocation();
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    if (
      loc.hash.includes("checklist") ||
      loc.hash.includes("gate-checklist") ||
      loc.hash.includes("stage-419")
    ) {
      setShowDetails(true);
    }
  }, [loc.hash]);

  return (
    <div className="page-stack mi-page mvp22-overview">
      <SimplifiedMarketDashboard />

      <div className="operator-details-toggle">
        <button
          type="button"
          className="ro-nav-chip"
          onClick={() => setShowDetails((v) => !v)}
          aria-expanded={showDetails}
        >
          {showDetails ? "Hide gate details" : "Show gate details"}
        </button>
      </div>

      {showDetails ? (
        <div className="operator-section desk-secondary" id="gate-checklist-detail">
          <h2 className="section-title">Checkpoint & gate</h2>
          <GateChecklistCard
            id="checklist-eth-watch-reappearance"
            title="ETH Watch Reappearance Checklist"
            items={ETH_WATCH_REAPPEARANCE_CHECKLIST}
            footer="All false under HOLD — wait for ETH watch · no 30m · no 60m · Stage 4.19 blocked"
          />
          <GateChecklistCard
            id="checklist-short-regression-approval"
            title="Short Regression Approval Checklist"
            items={SHORT_REGRESSION_CHECKLIST}
            footer="All false under HOLD — 30m now: false · 60m: false · Auto-run: false"
          />
          <GateChecklistCard
            id="checklist-stage-419-dossier"
            title="Stage 4.19 Dossier Checklist"
            items={STAGE_419_DOSSIER_CHECKLIST}
            footer="Dossier not started · no Stage 4.19 start button"
          />
        </div>
      ) : null}
    </div>
  );
}
