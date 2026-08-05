import type { LiveSlotBinding } from "./types";
import { isStale } from "./displayRules";

/**
 * Renders one live-bound value with mandatory lineage / freshness indicators.
 * Never shows UNAVAILABLE as 0.
 */
export function BoundLiveValue({
  binding,
  label,
}: {
  binding: LiveSlotBinding;
  label?: string;
}) {
  const stale = isStale(String(binding.freshness));
  const unavailable =
    binding.unavailable_indicator_present ||
    String(binding.freshness).toUpperCase() === "UNAVAILABLE" ||
    String(binding.freshness).toUpperCase() === "BLOCKED";

  const display =
    unavailable && (binding.display_value === "0" || binding.display_value === "0.0")
      ? "UNAVAILABLE"
      : binding.display_value;

  return (
    <article
      className="member-panel live-bound-value"
      data-component={binding.component_id}
      data-slot={binding.slot_id}
      data-freshness={binding.freshness}
      data-lineage={binding.lineage}
      data-source={binding.source}
    >
      {label ? <h2>{label}</h2> : null}
      <p className="member-metric-value" aria-live="polite">
        {display}
        {binding.unit ? <span className="muted sm"> {binding.unit}</span> : null}
      </p>
      <div className="member-card-meta live-meta">
        {stale ? (
          <span className="member-chip member-chip-stale" role="status">
            STALE
          </span>
        ) : null}
        {unavailable ? (
          <span className="member-chip member-chip-unavailable" role="status">
            {String(binding.freshness).toUpperCase() === "BLOCKED" ? "BLOCKED" : "UNAVAILABLE"}
          </span>
        ) : (
          <span className="member-chip">{binding.freshness}</span>
        )}
        <span className="member-chip">{binding.completeness}</span>
      </div>
      <p className="muted sm live-lineage">
        source={binding.source} · field={binding.field} · as_of={binding.as_of ?? "n/a"} ·
        retrieved={binding.retrieved_at} · quality={binding.quality} · lineage={binding.lineage} ·
        fallback={binding.fallback}
      </p>
    </article>
  );
}
