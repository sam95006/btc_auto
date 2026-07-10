import { AICommanderPanel } from "../components/AICommanderPanel";
import { DemoDataBadge } from "../components/DemoDataBadge";

export function AssistantPage() {
  return (
    <div>
      <header className="page-header">
        <h1>AI Assistant</h1>
        <DemoDataBadge />
        <p className="page-sub">
          Full-page stub. Desktop also shows the right AI rail. Demo answers only.
        </p>
      </header>
      <div className="panel-card" style={{ maxWidth: 720 }}>
        <p className="muted">
          Use the right rail on desktop, or the embedded panel below on narrow layouts.
        </p>
        <div style={{ marginTop: "1rem", border: "1px solid var(--border)", borderRadius: 8 }}>
          <AICommanderPanel />
        </div>
      </div>
    </div>
  );
}
