import { useState } from "react";
import type { EvidencePreset } from "../demo/evidencePresets";
import { presetAbsoluteHref, presetHref } from "../demo/evidencePresets";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge, type StatusTone } from "./StatusBadge";
import { Link } from "react-router-dom";

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  return false;
}

/** Single preset card: Open preset / Copy link only (MVP-19). */
export function EvidencePresetCard({
  preset,
  compact = false,
}: {
  preset: EvidencePreset;
  compact?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [fallback, setFallback] = useState<string | null>(null);
  const href = presetHref(preset);

  const onCopy = async () => {
    const abs = presetAbsoluteHref(preset);
    const ok = await copyText(abs);
    if (ok) {
      setCopied(true);
      setFallback(null);
      window.setTimeout(() => setCopied(false), 2000);
    } else {
      setFallback(abs);
    }
  };

  return (
    <article className={`panel-card dense-card evidence-preset-card${compact ? " compact" : ""}`}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0, fontSize: compact ? "0.85rem" : "0.95rem" }}>{preset.title}</h3>
        <StatusBadge tone={preset.pinTone as StatusTone}>{preset.pinStatusLabel}</StatusBadge>
        <span className="demo-badge">URL ONLY</span>
        <DemoDataBadge />
      </div>
      {!compact ? (
        <>
          <p className="muted">{preset.description}</p>
          <p className="muted">
            Use case: {preset.operatorUseCase}
          </p>
          <p className="mono muted">
            {preset.targetPage}?{preset.query}
            {preset.hash}
          </p>
        </>
      ) : (
        <p className="muted" style={{ marginBottom: "0.35rem" }}>
          {preset.description}
        </p>
      )}
      <div className="ro-nav-row">
        <Link className="ro-nav-chip" to={href}>
          Open preset
        </Link>
        <button type="button" className="ro-nav-chip as-button" onClick={onCopy}>
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      {fallback ? (
        <p className="mono muted" style={{ marginTop: "0.4rem", marginBottom: 0 }}>
          Clipboard unavailable — copy manually: {fallback}
        </p>
      ) : null}
      <p className="muted" style={{ marginTop: "0.4rem", marginBottom: 0, fontSize: "0.72rem" }}>
        {preset.safetyNote} · NOT INVESTMENT ADVICE · no trading controls
      </p>
    </article>
  );
}
