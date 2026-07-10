import type { ReflectionSummary } from "../types/nexus";
import { DemoDataBadge } from "./DemoDataBadge";

export function ReflectionSummaryCard({
  summary,
}: {
  summary: ReflectionSummary;
}) {
  return (
    <article className="panel-card">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Reflection Summary</h3>
        <DemoDataBadge />
      </div>
      <p className="muted">Mistakes</p>
      <ul>
        {summary.mistakes.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
      <p className="muted">Repeated errors</p>
      <ul>
        {summary.repeatedErrors.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
      <p>Confidence penalty: {summary.confidencePenalty}</p>
      <p>Size adjustment: {summary.sizeAdjustment}</p>
      <p>Behavior change: {summary.behaviorChange}</p>
      <p>Next patch (proposal only): {summary.nextPatchRecommendation}</p>
      <p className="muted">Applied: {summary.applied ? "yes" : "no (demo)"}</p>
    </article>
  );
}
