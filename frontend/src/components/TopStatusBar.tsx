import { getSystemStatus } from "../data/nexusDataAdapter";
import { DemoDataBadge } from "./DemoDataBadge";

export function TopStatusBar() {
  const s = getSystemStatus();
  return (
    <header className="top-status-bar">
      <div className="brand-mark">
        NEXUS / <span>EATI</span>
      </div>
      <span className="status-chip mode">{s.mode}</span>
      <span className="status-chip safety">{s.safetyLine}</span>
      <span className="status-chip">
        {s.stageReadiness} / {s.currentGate}
      </span>
      <span className="status-chip mono">Last Update: {s.lastUpdate}</span>
      <span className="status-chip disclaimer">{s.disclaimer}</span>
      <DemoDataBadge />
    </header>
  );
}
