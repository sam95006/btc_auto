/**
 * Live product — merges the former Command Center / Attention / Feed / Brief into
 * ONE product shell with tabs (overview / activity / brief). The shell stays put
 * (fixed min-height) so the layout never jumps; the user learns one interface.
 * Realtime status shown in the header. All data backend-driven.
 */
import { useState } from "react";
import { useRealtime } from "../../context/MarketContext";
import { useLocale } from "../../i18n";
import { AttentionPanel } from "./AttentionPanel";
import { CommandCenter } from "./CommandCenter";
import { IntelligenceFeed } from "./IntelligenceFeed";
import { MarketBrief } from "./MarketBrief";
import { RealtimePill } from "./RealtimePill";

export function LiveProduct() {
  const { t } = useLocale();
  const rt = useRealtime();
  const [tab, setTab] = useState<"overview" | "activity" | "brief">("overview");
  const tabs = [
    { id: "overview" as const, label: t("live_overview") },
    { id: "activity" as const, label: t("live_dynamics") },
    { id: "brief" as const, label: t("live_brief") },
  ];
  return (
    <section className="corp-fs-section" aria-labelledby="fs-live">
      <div className="corp-fs-inner wide">
        <div className="corp-fs-head"><div><div className="corp-fs-eyebrow">LIVE PRODUCT</div>
          <h2 className="corp-fs-h2" id="fs-live">{t("live_title")}</h2>
          <p className="corp-fs-sub">{t("live_sub")}</p></div></div>

        <div className="corp-lp" data-testid="live-product">
          <div className="corp-lp-top">
            <div className="corp-tabs" role="tablist" aria-label={t("live_title")}>
              {tabs.map((x) => (
                <button key={x.id} role="tab" aria-selected={tab === x.id} className="corp-tab" onClick={() => setTab(x.id)}>{x.label}</button>
              ))}
            </div>
            <RealtimePill rt={rt} />
          </div>
          <div className="corp-lp-body" role="tabpanel">
            {tab === "overview" ? (
              <CommandCenter />
            ) : tab === "activity" ? (
              <div style={{ display: "grid", gap: "1rem" }}>
                <AttentionPanel />
                <IntelligenceFeed />
              </div>
            ) : (
              <MarketBrief />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
