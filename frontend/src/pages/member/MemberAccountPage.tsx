import { Link } from "react-router-dom";
import { useState } from "react";
import { useT } from "../../i18n";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";
import { MEMBER_ACCOUNT_SUBNAV } from "../../member/routes";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import { loadUiDensity, saveUiDensity, type UiDensity } from "../../member/uiDensityPrefs";
import { PRODUCT_CAPABILITIES } from "../../product_v2/productCapabilities";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { MemberIdentityPanel } from "../../retention/MemberIdentityPanel";

/** Account — identity + display settings + capability upgrade entry (no Billing activation). */
export function MemberAccountPage() {
  const t = useT();
  const { loading, items } = usePageSlots([
    ["account.profile_card", "runtime", "Profile runtime"],
    ["account.locale_chip", "freshness", "Locale freshness"],
  ]);
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    saveUiDensity(d);
  };

  return (
    <MemberPageChrome titleKey="pages.account.title" subtitleKey="pages.account.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <MemberIdentityPanel />

      <section className="nx10-panel" style={{ marginTop: 16 }} data-testid="account-display-settings">
        <h2 className="nx-sec-title" style={{ marginTop: 0 }}>
          顯示設定
        </h2>
        <p className="muted sm">{t("ui.density.accountHint")}</p>
        <div style={{ marginTop: 12 }}>
          <div className="nx10-account-density">
            <UiDensityToggle density={density} onDensityChange={onDensity} />
          </div>
        </div>
      </section>

      <section className="member-panel" style={{ marginTop: 16 }} data-testid="account-upgrade-entry">
        <h2 className="nx-sec-title">方案能力</h2>
        <p className="muted sm">
          目前預覽方案：{plan} · 價格未定 · Billing 尚未啟用 · 僅顯示已存在或標示即將推出的能力
        </p>
        <div className="mp2-capability-matrix">
          {(
            [
              ["FREE", PRODUCT_CAPABILITIES.FREE],
              ["PRO", PRODUCT_CAPABILITIES.PRO],
              ["RESEARCH", PRODUCT_CAPABILITIES.RESEARCH],
            ] as const
          ).map(([name, list]) => (
            <div key={name} className="mp2-capability-col" data-plan={name}>
              <h3>{name}</h3>
              <ul>
                {list.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mp2-actions" style={{ marginTop: 12 }}>
          <Link to="/review" className="mp2-btn mp2-btn-primary">
            查看方案比較
          </Link>
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
