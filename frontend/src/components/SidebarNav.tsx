import { NavLink } from "react-router-dom";
import { useState } from "react";
import { useI18n, useT, type LocaleCode } from "../i18n";
import { MEMBER_ACCOUNT_SUBNAV, MEMBER_NAV } from "../member/routes";

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

export function MobileBottomNav() {
  const t = useT();
  const primary = MEMBER_NAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const account = MEMBER_ACCOUNT_SUBNAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.labelKey),
  }));
  const primaryFive = primary.slice(0, 4);
  return (
    <nav className="w4-mobile-bottom-nav member-mobile-nav" aria-label={t("a11y.mobileNav")}>
      {primaryFive.map((l) => (
        <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
          <span>{l.short}</span>
        </NavLink>
      ))}
      <details className="w4-mobile-more">
        <summary>{t("nav.more")}</summary>
        <div className="w4-mobile-more-panel">
          {primary.slice(4).map((l) => (
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

export function SidebarNav() {
  const t = useT();
  const [accountOpen, setAccountOpen] = useState(true);
  const primary: NavItem[] = MEMBER_NAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const account: NavItem[] = MEMBER_ACCOUNT_SUBNAV.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.labelKey),
  }));

  return (
    <>
      <nav
        className="sidebar-nav sidebar-nav-compact nx-nav-member"
        aria-label={t("a11y.mainNav")}
      >
        <div className="sidebar-brand-block">
          <div className="sidebar-product">{t("brand.product")}</div>
          <div className="sidebar-product-sub muted">{t("brand.memberPlatform")}</div>
          <LocaleSwitcher />
        </div>
        <div className="nav-group">
          <div className="nav-label">{t("brand.decisionIntegrity")}</div>
          <Links items={primary} />
        </div>
        <div className="nav-group">
          <button
            type="button"
            className="nav-collapse-btn"
            aria-expanded={accountOpen}
            aria-controls="member-account-nav"
            onClick={() => setAccountOpen((v) => !v)}
          >
            {t("a11y.accountNav")} {accountOpen ? "▾" : "▸"}
          </button>
          {accountOpen ? (
            <div id="member-account-nav">
              <Links items={account} />
            </div>
          ) : null}
        </div>
      </nav>
      <MobileBottomNav />
    </>
  );
}
