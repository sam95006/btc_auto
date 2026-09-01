/**
 * "你可以用 NEXUS 做三件事" — three jobs, ONE shared product panel that changes
 * with the selected task (watch market / find what matters / control risk).
 * All data backend-driven via the realtime context. Progressive disclosure:
 * the panel swaps content instead of stacking three sections.
 */
import { useState } from "react";
import { useMarket } from "../../context/MarketContext";
import { useLocale } from "../../i18n";
import { symOf } from "../../lib/format";
import { AttentionPanel } from "./AttentionPanel";
import { MarketStrip } from "./MarketStrip";

const REGIME_L: Record<string, Record<string, string>> = {
  "zh-TW": { RISK_ON: "偏多", RISK_OFF: "防禦", NEUTRAL: "中性" },
  "en-US": { RISK_ON: "Risk-On", RISK_OFF: "Risk-Off", NEUTRAL: "Neutral" },
  "ja-JP": { RISK_ON: "リスクオン", RISK_OFF: "リスクオフ", NEUTRAL: "中立" },
  "ko-KR": { RISK_ON: "위험선호", RISK_OFF: "위험회피", NEUTRAL: "중립" },
};

function RiskView() {
  const m = useMarket();
  const { locale, t } = useLocale();
  if (m.status !== "READY") return <div className="corp-fs-loading" role="status">{t("st_loading")}</div>;
  const regime = m.data.regime?.value ?? null;
  const risk = m.data.risk?.value ?? null;
  return (
    <div className="corp-fs-metrics" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <div className="corp-fs-metric"><div className="k">Regime</div><div className="v" data-state={regime ?? undefined}>{regime ? (REGIME_L[locale]?.[regime] ?? regime) : "—"}</div></div>
      <div className="corp-fs-metric"><div className="k">Risk</div><div className={`v ${risk === "elevated" ? "warn" : ""} ${risk ? "" : "muted"}`}>{risk ?? "—"}</div></div>
      {m.data.symbols.map((s) => (
        <div className="corp-fs-metric" key={s.symbol}>
          <div className="k">{symOf(s.symbol)} · Vol</div>
          <div className={`v ${s.volatility === "high" ? "warn" : ""} ${s.volatility ? "" : "muted"}`}>{s.volatility ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}

export function JobsSection() {
  const { t } = useLocale();
  const [tab, setTab] = useState<"watch" | "find" | "risk">("watch");
  const jobs = [
    { id: "watch" as const, label: t("jobs_watch"), desc: t("jobs_watch_d") },
    { id: "find" as const, label: t("jobs_find"), desc: t("jobs_find_d") },
    { id: "risk" as const, label: t("jobs_risk"), desc: t("jobs_risk_d") },
  ];
  const active = jobs.find((j) => j.id === tab)!;
  return (
    <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-jobs">
      <div className="corp-fs-inner">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">WHAT YOU CAN DO</div>
          <h2 className="corp-fs-h2" id="fs-jobs">{t("jobs_title")}</h2></div></div>
        <div className="corp-jobs">
          <div>
            <div className="corp-tabs" role="tablist" aria-label={t("jobs_title")}>
              {jobs.map((j) => (
                <button key={j.id} role="tab" aria-selected={tab === j.id} className="corp-tab" onClick={() => setTab(j.id)}>{j.label}</button>
              ))}
            </div>
            <p className="corp-jobs-desc">{active.desc}</p>
          </div>
          <div className="corp-jobs-panel" role="tabpanel">
            {tab === "watch" ? <MarketStrip /> : tab === "find" ? <AttentionPanel /> : <RiskView />}
          </div>
        </div>
      </div>
    </section>
  );
}
