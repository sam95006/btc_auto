import type { FunnelStage } from "./types";

export function IntelligenceFunnel({
  stages,
  summary,
  sourceMode,
}: {
  stages: FunnelStage[];
  summary: string;
  sourceMode: string;
}) {
  return (
    <section
      className="member-intel-funnel"
      aria-label="Decision intelligence funnel"
      data-source-mode={sourceMode}
      data-testid="member-intel-funnel"
    >
      <header className="member-intel-funnel-head">
        <h3>Funnel</h3>
        <span className="member-intel-mode-chip" data-mode={sourceMode}>
          {sourceMode === "LIVE" ? "LIVE" : sourceMode}
        </span>
      </header>
      <ol className="member-intel-funnel-list">
        {stages.map((s) => (
          <li key={s.key} data-available={s.available ? "true" : "false"}>
            <span className="member-intel-funnel-label">{s.label}</span>
            <strong
              className={
                s.available ? "member-intel-funnel-count" : "member-intel-funnel-unavailable"
              }
              data-display={s.display}
            >
              {s.display}
            </strong>
          </li>
        ))}
      </ol>
      <p className="muted sm member-intel-funnel-summary">{summary}</p>
    </section>
  );
}
