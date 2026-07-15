import { Link } from "react-router-dom";
import { EVIDENCE_PRESETS, presetHref } from "../demo/evidencePresets";
import { DemoDataBadge } from "./DemoDataBadge";
import { EvidencePresetCard } from "./EvidencePresetCard";

/** Chip bar of static Evidence share presets (MVP-19) — URL navigation only. */
export function EvidencePresetBar({ showCards = true }: { showCards?: boolean }) {
  return (
    <section id="evidence-presets" className="panel-card dense-card evidence-preset-bar">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0, fontSize: "0.95rem" }}>Evidence Share Presets</h3>
        <span className="demo-badge">URL ONLY</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: "0.35rem" }}>
        One-click workspace views · updates query + hash · no backend · no /data · no trading controls
        · NOT INVESTMENT ADVICE
      </p>
      <div className="preset-chip-row">
        {EVIDENCE_PRESETS.map((p) => (
          <Link key={p.id} className="preset-chip" to={presetHref(p)} title={p.description}>
            {p.title}
          </Link>
        ))}
      </div>
      {showCards ? (
        <div className="preset-card-grid">
          {EVIDENCE_PRESETS.map((p) => (
            <EvidencePresetCard key={p.id} preset={p} compact />
          ))}
        </div>
      ) : null}
    </section>
  );
}
