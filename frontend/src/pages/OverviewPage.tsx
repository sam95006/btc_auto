import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { DecisionMarketOverview } from "../components/DecisionMarketOverview";
import { NexusMarketIntelligenceCards } from "../components/NexusMarketIntelligenceCards";
import { ProductSimpleView } from "../components/ProductSimpleView";
import {
  ETH_WATCH_REAPPEARANCE_CHECKLIST,
  SHORT_REGRESSION_CHECKLIST,
  STAGE_419_DOSSIER_CHECKLIST,
} from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import { loadViewMode, type ViewMode } from "../market/viewPrefs";

/**
 * Product 7 Overview — Simple View first screen, then Pro / research layers.
 */
export function OverviewPage() {
  useHashScroll();
  const loc = useLocation();
  const [showDetails, setShowDetails] = useState(false);
  const [view, setView] = useState<ViewMode>(() => loadViewMode());

  useEffect(() => {
    if (
      loc.hash.includes("checklist") ||
      loc.hash.includes("gate-checklist") ||
      loc.hash.includes("stage-419")
    ) {
      setShowDetails(true);
    }
  }, [loc.hash]);

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple" || mode === "advanced") setView(mode);
    };
    window.addEventListener("nexus-view-mode", onView);
    return () => window.removeEventListener("nexus-view-mode", onView);
  }, []);

  const simple = view === "simple";

  return (
    <div className="page-stack mi-page mvp22-overview nx-product-overview nx-product7">
      {simple ? <ProductSimpleView /> : null}

      <details className="nx-p7-pro-layer" open={!simple}>
        <summary className="muted">{simple ? "展開 Pro／研究層（圖表、版塊、掃描）" : "Pro View · 研究層"}</summary>
        <DecisionMarketOverview />
        <NexusMarketIntelligenceCards />
      </details>

      <details
        className="operator-details-toggle"
        open={showDetails}
        onToggle={(e) => setShowDetails((e.target as HTMLDetailsElement).open)}
      >
        <summary className="muted">Gate checklists (optional)</summary>
        <div className="operator-section desk-secondary" id="gate-checklist-detail">
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
      </details>
    </div>
  );
}
