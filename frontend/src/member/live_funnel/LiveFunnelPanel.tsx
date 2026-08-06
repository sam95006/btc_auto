import type { FunnelStage } from "./liveFunnelModels";

/** Read-only 9-stage Live Funnel (scanned → … → Shadow Decisions). */
export function LiveFunnelPanel({
  stages,
  summary,
  dataClass,
}: {
  stages: FunnelStage[];
  summary: string;
  dataClass: string;
}) {
  return (
    <section
      className="member-live-funnel"
      aria-label="Live read-only decision funnel"
      data-testid="live-funnel-panel"
      data-class={dataClass}
    >
      <header className="member-live-funnel-head">
        <h3>Live Funnel · read-only</h3>
        <span className="member-chip" data-testid="live-funnel-data-class" data-class={dataClass}>
          {dataClass}
        </span>
      </header>
      <ol className="member-live-funnel-list" data-testid="live-funnel-stages">
        {stages.map((s) => (
          <li key={s.id} data-stage={s.id} data-available={s.available ? "true" : "false"}>
            <span className="member-live-funnel-label">{s.label}</span>
            <strong
              className={
                s.available ? "member-live-funnel-count" : "member-live-funnel-unavailable"
              }
              data-display={s.display}
            >
              {s.display}
            </strong>
          </li>
        ))}
      </ol>
      <p className="muted sm" data-testid="live-funnel-summary">
        {summary}
      </p>
      <p className="muted sm">
        Shadow Decisions are research-only — not exchange orders. No trade buttons.
      </p>
    </section>
  );
}
