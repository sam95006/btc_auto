import { Link } from "react-router-dom";
import { PaperDecisionFunnelPanel } from "../components/PaperDecisionFunnelPanel";

/** Phase 6.5 — Trade plan (PAPER / shadow only, no founder execution controls). */
export function TradePlanPage() {
  return (
    <div className="page-stack">
      <header>
        <h1>交易計畫</h1>
        <p className="muted">AI direction + PAPER simulation — no live execution controls.</p>
      </header>
      <PaperDecisionFunnelPanel />
      <p>
        <Link to="/paper-lab">PAPER Lab</Link> · <Link to="/performance">績效</Link>
      </p>
    </div>
  );
}
