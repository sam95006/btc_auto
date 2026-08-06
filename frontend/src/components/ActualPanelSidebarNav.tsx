import { NavLink } from "react-router-dom";
import { useState } from "react";
import { useI18n, useT, type LocaleCode } from "../i18n";
import { usePublicEntitlements } from "../member/public_entitlements_v18_2";
import { isPreviewEntitlementReviewAvailable } from "../member/previewEntitlementReview";
import { usePreviewReviewPlan } from "../member/usePreviewReviewPlan";
import {
  ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1,
  MOBILE_BOTTOM_PRIMARY_V18_2_1,
  PRIMARY_ACTUAL_PANEL_NAV_V18_2_1,
  UTILITY_ACTUAL_PANEL_NAV_V18_2_1,
} from "../member/navigationContractV18_2_1";
import { MEMBER_ACCOUNT_SUBNAV } from "../member/routes";

type NavItem = { to: string; label: string; short: string };

function Links({ items }: { items: NavItem[] }) {
  return (
    <>
      {items.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => (isActive ? "active" : undefined)}
          title={l.label}
          end={l.to === "/account"}
        >
          <span className="nav-text-full">{l.label}</span>
          <span className="nav-text-short">{l.short}</span>
        </NavLink>
      ))}
    </>
  );
}

function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n();
  const options: LocaleCode[] = ["zh-TW", "en"];
  return (
    <div className="nx-locale-switcher" role="group" aria-label={t("a11y.localeSwitcher")}>
      {options.map((code) => (
        <button
          key={code}
          type="button"
          aria-pressed={locale === code}
          onClick={() => setLocale(code)}
        >
          {code === "zh-TW" ? t("locale.zhTW") : t("locale.en")}
        </button>
      ))}
    </div>
  );
}

export function ActualPanelMobileBottomNav() {
  const t = useT();
  const primary = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const mobilePaths = new Set<string>(MOBILE_BOTTOM_PRIMARY_V18_2_1);
  const bottom = primary.filter((p) => mobilePaths.has(p.to));
  const overflow = primary.filter((p) => !mobilePaths.has(p.to));
  const utility = UTILITY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const account = MEMBER_ACCOUNT_SUBNAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.labelKey),
  }));

  return (
    <nav className="w4-mobile-bottom-nav member-mobile-nav" aria-label={t("a11y.mobileNav")}>
      {bottom.map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
          <span>{l.short}</span>
        </NavLink>
      ))}
      <details className="w4-mobile-more">
        <summary>{t("nav.more")}</summary>
        <div className="w4-mobile-more-panel">
          {overflow.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
          {utility.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
          {account.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}

export function ActualPanelSidebarNav() {
  const t = useT();
  const [accountOpen, setAccountOpen] = useState(true);
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const showReviewLink = isPreviewEntitlementReviewAvailable();
  const showOrg = plan === "ENTERPRISE";

  const primary: NavItem[] = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const utility: NavItem[] = UTILITY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const enterprise: NavItem[] = showOrg
    ? ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
        to: i.to,
        label: t(i.labelKey),
        short: t(i.shortKey),
      }))
    : [];
  const account: NavItem[] = MEMBER_ACCOUNT_SUBNAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.labelKey),
  }));

  return (
    <>
      <nav className="sidebar-nav sidebar-nav-compact nx-nav-member" aria-label={t("a11y.mainNav")}>
        <div className="sidebar-brand-block">
          <div className="sidebar-product">{t("brand.liveMarket")}</div>
          <div className="sidebar-product-sub muted">{t("brand.liveMarketSub")}</div>
          <LocaleSwitcher />
        </div>
        <div className="nav-group">
          <div className="nav-label">{t("nav.v182.primaryLabel")}</div>
          <Links items={primary} />
        </div>
        <div className="nav-group">
          <div className="nav-label">{t("nav.v182.utilityLabel")}</div>
          <Links items={utility} />
          {showReviewLink ? (
            <NavLink
              to="/preview/v18_2_1/review"
              className={({ isActive }) => (isActive ? "active" : undefined)}
              data-testid="nav-membership-review"
            >
              <span className="nav-text-full">Membership review</span>
              <span className="nav-text-short">Review</span>
            </NavLink>
          ) : null}
        </div>
        {enterprise.length ? (
          <div className="nav-group">
            <div className="nav-label">{t("nav.v182.enterpriseLabel")}</div>
            <Links items={enterprise} />
          </div>
        ) : null}
        <div className="nav-group">
          <button
            type="button"
            className="nav-collapse-btn"
            aria-expanded={accountOpen}
            aria-controls="actual-panel-account-nav"
            onClick={() => setAccountOpen((v) => !v)}
          >
            {t("a11y.accountNav")} {accountOpen ? "▾" : "▸"}
          </button>
          {accountOpen ? (
            <div id="actual-panel-account-nav">
              <Links items={account} />
            </div>
          ) : null}
        </div>
      </nav>
      <ActualPanelMobileBottomNav />
    </>
  );
}
