/**
 * Signal / Anomaly / Risk + AI capability scene. NEXUS-style intelligence
 * cards — NOT DataHunterX cards, and NOT seeded with fake example signals.
 * Each card states honestly whether it is LIVE today (backed by the current
 * backend market API) or a platform CAPABILITY delivered inside the member
 * products. The AI card describes member-safe assistance only — it never
 * exposes private trading AI, credentials, lessons, or Founder strategy.
 */
import { useMarket } from "../../context/MarketContext";
import { useReveal } from "../../hooks/useCorporate";

type Cap = { title: string; body: string; live: boolean };

export function CapabilityScene() {
  const m = useMarket();
  const { ref, shown } = useReveal<HTMLDivElement>();
  // Regime & risk are genuinely live today; signal/anomaly are member-product
  // capabilities not exposed as live values on the public site.
  const marketLive = m.status === "READY";

  const caps: Cap[] = [
    {
      title: "Regime & Risk",
      body: "Backend-decided market regime and risk posture across instruments, with provenance on every value.",
      live: marketLive,
    },
    {
      title: "Signal",
      body: "Direction and strength summaries inside the member products — member-safe, never autonomous execution.",
      live: false,
    },
    {
      title: "Anomaly",
      body: "Structural anomaly detection surfaced to members. Public examples are never fabricated here.",
      live: false,
    },
    {
      title: "AI Intelligence",
      body: "AI helps read market context, normalize evidence and explain risk in human-readable terms. Public members never receive autonomous trading.",
      live: false,
    },
  ];

  return (
    <section className="corp-section" aria-labelledby="corp-cap-h">
      <div className="corp-section-inner" ref={ref}>
        <div className={`corp-reveal ${shown ? "is-shown" : ""}`} style={{ ["--p" as string]: shown ? "1" : "0" }}>
          <div className="corp-eyebrow">SIGNAL · ANOMALY · RISK · AI</div>
          <h2 className="corp-h2" id="corp-cap-h">情報能力，誠實標示 / Intelligence capabilities, honestly labelled</h2>
          <p className="corp-lead">
            We show what is live today and what is delivered inside the member products — clearly separated, with no
            fabricated examples and no private execution.
          </p>
        </div>
        <div className="corp-caps">
          {caps.map((c) => (
            <div key={c.title} className="corp-cap" data-testid="cap-card">
              <h3>{c.title}</h3>
              <p>{c.body}</p>
              <span className={`corp-cap-state ${c.live ? "live" : "capability"}`}>
                {c.live ? "LIVE" : "CAPABILITY"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
