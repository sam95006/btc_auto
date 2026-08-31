/**
 * Platform architecture scene: PUBLIC MARKET DATA → NORMALIZATION → CONTEXT →
 * RISK → INTELLIGENCE, progressively lit by scroll. Communicates the pipeline
 * WITHOUT exposing any private strategy internals or Founder trading. The final
 * "Intelligence" stage branches into the Personal and Enterprise products.
 */
import { useRevealVar, useStageProgress } from "../../hooks/useScrollScene";

const STAGES = [
  { k: "01 · INGEST", t: "Public Market Data", d: "Credential-free public feeds — source & freshness on every value." },
  { k: "02 · NORMALIZE", t: "Normalization", d: "Deterministic cleaning into a comparable structure." },
  { k: "03 · CONTEXT", t: "Context", d: "Cross-instrument regime & positioning context." },
  { k: "04 · RISK", t: "Risk", d: "Backend-decided risk posture, never fabricated." },
  { k: "05 · SYNTHESIS", t: "Intelligence", d: "Member-safe, human-readable synthesis." },
];

export function IntelligenceEngineScene() {
  const reveal = useRevealVar<HTMLDivElement>();
  const { ref, progress } = useStageProgress<HTMLDivElement>();
  const lit = Math.min(STAGES.length, Math.ceil(progress * STAGES.length) + 1);

  return (
    <section className="corp-section" aria-labelledby="corp-engine-h">
      <div className="corp-section-inner" ref={reveal}>
        <div className="corp-reveal">
          <div className="corp-eyebrow">LIVE INTELLIGENCE ENGINE</div>
          <h2 className="corp-h2" id="corp-engine-h">從公開數據到可判斷的情報 / From public data to decision-grade intelligence</h2>
          <p className="corp-lead">
            One deterministic pipeline turns credential-free public market data into member-safe intelligence —
            with provenance at the input and a clear product boundary at the output. Private execution is never part of this path.
          </p>
        </div>

        <div className="corp-engine" ref={ref}>
          <div className="corp-pipe" role="list">
            {STAGES.map((s, i) => (
              <div key={s.t} role="listitem" className={`corp-pipe-node ${i < lit ? "is-lit" : ""}`}>
                <div className="k">{s.k}</div>
                <div className="t">{s.t}</div>
                <div className="d">{s.d}</div>
              </div>
            ))}
          </div>
          <p className="corp-editor-hint" style={{ textAlign: "center" }}>
            公開數據 · 讀取權限 / read-only public intelligence — 不含私有交易或 Founder 策略
          </p>
        </div>
      </div>
    </section>
  );
}
