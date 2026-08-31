/**
 * "Price is one layer" scroll story. As the user scrolls, deeper structure
 * layers activate. Each layer is tagged LIVE (backed by the current backend
 * showcase) or CONCEPT (educational capability the backend does not currently
 * expose as live values) — we never render fake OI/CVD/funding numbers.
 */
import { useMarket } from "../../context/MarketContext";
import { useRevealVar, useStageProgress } from "../../hooks/useScrollScene";

type Layer = { name: string; desc: string; live: boolean };

// LIVE flags reflect what /api/corporate/v1/market actually provides today.
const LAYERS: Layer[] = [
  { name: "Price", desc: "The surface everyone sees — last traded price.", live: true },
  { name: "Volatility", desc: "24h range translated into a volatility band.", live: true },
  { name: "Regime", desc: "Backend-decided market regime across instruments.", live: true },
  { name: "Risk", desc: "Aggregate risk posture derived from range.", live: true },
  { name: "Flow / Positioning", desc: "Order-flow & positioning structure — capability, not shown as live values.", live: false },
  { name: "Context", desc: "Cross-instrument context and narrative synthesis.", live: false },
  { name: "Anomaly", desc: "Structural anomaly detection — member-facing capability.", live: false },
  { name: "Intelligence", desc: "The member-safe synthesis of every layer above.", live: false },
];

export function MarketStructureScene() {
  const m = useMarket();
  const { ref, progress } = useStageProgress<HTMLDivElement>();
  const reveal = useRevealVar<HTMLDivElement>();
  const active = Math.min(LAYERS.length - 1, Math.floor(progress * LAYERS.length));
  const regime = m.status === "READY" ? m.data.regime?.value ?? null : null;

  return (
    <section className="corp-section corp-structure" aria-labelledby="corp-structure-h">
      <div className="corp-section-inner" ref={reveal}>
        <div className="corp-reveal">
          <div className="corp-eyebrow">MARKET STRUCTURE</div>
          <h2 className="corp-h2" id="corp-structure-h">價格只是最上層 / Price is only the top layer</h2>
          <p className="corp-lead">
            Most tools stop at price. We render the structure beneath it — and we label exactly which
            layers are <strong>live</strong> today and which are platform capability, so nothing is ever implied.
          </p>
        </div>

        <div className="corp-structure-stage" ref={ref}>
          <div className="corp-structure-visual" aria-hidden>
            <div className="corp-strata" data-regime={regime ?? "none"} style={{ ["--active" as string]: String(active) }}>
              {LAYERS.map((l, i) => (
                <div
                  key={l.name}
                  className="corp-stratum"
                  style={{
                    opacity: i <= active ? 1 : 0.18,
                    transform: `translateY(${(i - active) * 2}px)`,
                  }}
                />
              ))}
            </div>
          </div>

          <div className="corp-layers" role="list">
            {LAYERS.map((l, i) => (
              <div key={l.name} role="listitem" className={`corp-layer ${i === active ? "is-active" : ""}`}>
                <span className="corp-layer-idx">{String(i + 1).padStart(2, "0")}</span>
                <span>
                  <span className="corp-layer-name">{l.name}</span>
                  <span className="corp-layer-desc">{l.desc}</span>
                </span>
                <span className={`corp-layer-tag ${l.live ? "is-live" : "is-concept"}`}>
                  {l.live ? "LIVE" : "CONCEPT"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
