import { NavLink, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useI18n, useT, type LocaleCode } from "../i18n";
import { usePublicEntitlements } from "../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../member/usePreviewReviewPlan";
import {
  ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1,
  MOBILE_BOTTOM_PRIMARY_V18_2_1,
  PRIMARY_ACTUAL_PANEL_NAV_V18_2_1,
  UTILITY_ACTUAL_PANEL_NAV_V18_2_1,
} from "../member/navigationContractV18_2_1";

type NavItem = { to: string; label: string; short: string; glyph: string };

const GLYPHS: Record<string, string> = {
  "/overview": "◉",
  "/opportunities": "◎",
  "/scanner": "▦",
  "/alerts": "⚑",
  "/intelligence": "◈",
  "/watchlist": "☆",
  "/assistant": "✦",
  "/account": "◎",
  "/organization": "▣",
};

function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n();
  const options: LocaleCode[] = ["zh-TW", "en"];
  return (
    <div className="nx10-locale" role="group" aria-label={t("a11y.localeSwitcher")}>
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

function RailLinks({ items, expanded }: { items: NavItem[]; expanded: boolean }) {
  return (
    <>
      {items.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => `nx10-rail-link${isActive ? " is-active" : ""}`}
          title={l.label}
          end={l.to === "/account"}
        >
          <span className="nx10-rail-glyph" aria-hidden>
            {l.glyph}
          </span>
          {expanded ? <span className="nx10-rail-label">{l.label}</span> : null}
          {!expanded ? <span className="sr-only">{l.label}</span> : null}
        </NavLink>
      ))}
    </>
  );
}

/** Mobile: 總覽/找機會/掃描/警報 · More: 研究/自選/AI/帳戶 */
export function ActualPanelMobileBottomNav() {
  const t = useT();
  const primary = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
    to: i.to,
    label: t(i.labelKey),
    short: t(i.shortKey),
  }));
  const mobilePaths = new Set<string>(MOBILE_BOTTOM_PRIMARY_V18_2_1);
  const bottom = primary.filter((p) => mobilePaths.has(p.to));
  const moreItems = [
    ...primary.filter((p) => !mobilePaths.has(p.to)),
    ...UTILITY_ACTUAL_PANEL_NAV_V18_2_1.map((i) => ({
      to: i.to,
      label: t(i.labelKey),
      short: t(i.shortKey),
    })),
  ];

  return (
    <nav className="nx10-mobile-nav" aria-label={t("a11y.mobileNav")}>
      {bottom.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) => (isActive ? "is-active" : undefined)}
        >
          <span>{l.short}</span>
        </NavLink>
      ))}
      <details className="nx10-mobile-more">
        <summary>{t("nav.more")}</summary>
        <div className="nx10-mobile-more-panel">
          {moreItems.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.label}
            </NavLink>
          ))}
        </div>
      </details>
    </nav>
  );
}

const RAIL_KEY = "nexus.v1828.railExpanded";

/** V18.2.10 compact expandable rail. Desktop only — hidden on mobile. */
export function ActualPanelSidebarNav() {
  const t = useT();
  const [expanded, setExpanded] = useState(() => {
    try {
      return localStorage.getItem(RAIL_KEY) === "1";
    } catch {
      return false;
    }
  });
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const showOrg = plan === "ENTERPRISE";

  useEffect(() => {
    try {
      localStorage.setItem(RAIL_KEY, expanded ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [expanded]);

  const toItem = (to: string, label: string, short: string): NavItem => ({
    to,
    label,
    short,
    glyph: GLYPHS[to] || "•",
  });

  const primary: NavItem[] = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.map((i) =>
    toItem(i.to, t(i.labelKey), t(i.shortKey)),
  );
  const utility: NavItem[] = UTILITY_ACTUAL_PANEL_NAV_V18_2_1.map((i) =>
    toItem(i.to, t(i.labelKey), t(i.shortKey)),
  );
  const enterprise: NavItem[] = showOrg
    ? ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1.map((i) => toItem(i.to, t(i.labelKey), t(i.shortKey)))
    : [];

  return (
    <>
      <nav
        className={`nx10-rail${expanded ? " is-expanded" : ""}`}
        aria-label={t("a11y.mainNav")}
        data-expanded={expanded ? "1" : "0"}
      >
        <button
          type="button"
          className="nx10-rail-toggle"
          aria-expanded={expanded}
          aria-label={expanded ? t("nav.v182.collapseRail") : t("nav.v182.expandRail")}
          onClick={() => setExpanded((v) => !v)}
        >
          <span aria-hidden>{expanded ? "‹" : "›"}</span>
        </button>

        <div className="nx10-rail-group">
          {expanded ? <div className="nx10-rail-group-label">{t("nav.v182.primaryLabel")}</div> : null}
          <RailLinks items={primary} expanded={expanded} />
        </div>

        <div className="nx10-rail-group">
          {expanded ? <div className="nx10-rail-group-label">{t("nav.v182.utilityLabel")}</div> : null}
          <RailLinks items={utility} expanded={expanded} />
        </div>

        {enterprise.length ? (
          <div className="nx10-rail-group" data-testid="nav-enterprise-org">
            {expanded ? (
              <div className="nx10-rail-group-label">{t("nav.v182.enterpriseLabel")}</div>
            ) : null}
            <RailLinks items={enterprise} expanded={expanded} />
          </div>
        ) : null}

        <div className="nx10-rail-foot">
          {expanded ? <LocaleSwitcher /> : null}
          <Link to="/account" className="nx10-rail-account muted">
            {expanded ? t("nav.account") : "A"}
          </Link>
        </div>
      </nav>
      <ActualPanelMobileBottomNav />
    </>
  );
}
