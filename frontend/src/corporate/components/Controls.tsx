/** Header controls: theme (System/Light/Dark) + language (one active locale).
 * Preferences are persisted locally (non-sensitive). Accessible menus. */
import { useEffect, useRef, useState } from "react";
import { useTheme, type ThemeMode } from "../context/ThemeContext";
import { LOCALES, LOCALE_NAMES, useLocale, type Locale } from "../i18n";

function useOutside(onClose: () => void) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", h); document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [onClose]);
  return ref;
}

function SunMoon({ resolved }: { resolved: "light" | "dark" }) {
  return resolved === "dark" ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.7" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
  );
}

export function ThemeControl() {
  const { mode, resolved, setMode, } = useTheme();
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  const items: [ThemeMode, string][] = [["system", t("theme_system")], ["light", t("theme_light")], ["dark", t("theme_dark")]];
  return (
    <div className="corp-menu-wrap" ref={ref}>
      <button className="corp-ctrl-btn" aria-haspopup="menu" aria-expanded={open} aria-label={t("theme_label")} onClick={() => setOpen((v) => !v)}>
        <SunMoon resolved={resolved} />
      </button>
      {open ? (
        <div className="corp-menu" role="menu">
          {items.map(([m, label]) => (
            <button key={m} role="menuitemradio" aria-checked={mode === m} onClick={() => { setMode(m); setOpen(false); }}>
              <span>{label}</span>{mode === m ? <span>✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function LocaleControl() {
  const { locale, setLocale, t } = useLocale();
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  return (
    <div className="corp-menu-wrap" ref={ref}>
      <button className="corp-ctrl-btn" aria-haspopup="menu" aria-expanded={open} aria-label={t("lang_label")} onClick={() => setOpen((v) => !v)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3c2.5 2.5 2.5 15.5 0 18M12 3c-2.5 2.5-2.5 15.5 0 18" stroke="currentColor" strokeWidth="1.6" /></svg>
        <span style={{ fontSize: "0.78rem" }}>{locale.split("-")[0].toUpperCase()}</span>
      </button>
      {open ? (
        <div className="corp-menu" role="menu">
          {LOCALES.map((l: Locale) => (
            <button key={l} role="menuitemradio" aria-checked={locale === l} onClick={() => { setLocale(l); setOpen(false); }}>
              <span>{LOCALE_NAMES[l]}</span>{locale === l ? <span>✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
