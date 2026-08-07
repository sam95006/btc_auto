import { Link } from "react-router-dom";
import { useState } from "react";
import { useT } from "../../i18n";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";
import { MEMBER_ACCOUNT_SUBNAV } from "../../member/routes";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import { loadUiDensity, saveUiDensity, type UiDensity } from "../../member/uiDensityPrefs";

/** Account — display settings host density preference (not chrome mode-first UX). */
export function MemberAccountPage() {
  const t = useT();
  const { loading, items } = usePageSlots([
    ["account.profile_card", "runtime", "Profile runtime"],
    ["account.locale_chip", "freshness", "Locale freshness"],
  ]);
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    saveUiDensity(d);
  };

  return (
    <MemberPageChrome titleKey="pages.account.title" subtitleKey="pages.account.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">
        Profile fields UNAVAILABLE until auth realm binds · no synthetic live profile.
      </p>

      <section className="v1828-ov-block" style={{ marginTop: 16 }} data-testid="account-display-settings">
        <h2 className="nx-sec-title" style={{ marginTop: 0 }}>
          顯示設定
        </h2>
        <p className="muted sm">{t("ui.density.accountHint")}</p>
        <div style={{ marginTop: 12 }}>
          {/* Density lives here only — not in command bar / overview chrome */}
          <div className="v1828-account-density">
            <UiDensityToggle density={density} onDensityChange={onDensity} />
          </div>
        </div>
      </section>

      <section className="member-panel" style={{ marginTop: 16 }}>
        <h2 className="nx-sec-title">Account links</h2>
        <ul className="member-link-grid">
          {MEMBER_ACCOUNT_SUBNAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{t(item.labelKey)}</Link>
            </li>
          ))}
        </ul>
      </section>
    </MemberPageChrome>
  );
}
