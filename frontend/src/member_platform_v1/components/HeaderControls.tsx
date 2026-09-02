/** NEXUS-EXPERIENCE-1B — view-mode + theme + locale controls and a Universal
 * Command Bar for the Personal app shell. The command bar navigates to assets/
 * routes that genuinely exist; unsupported AI screening is honest COMING_SOON. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LOCALES, LOCALE_NAMES, useExperience, type Locale, type ThemeMode, type ViewMode,
} from "../context/NexusExperience";

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

const ASSETS = ["BTC", "ETH", "SOL"];

export function CommandBar() {
  const { t } = useExperience();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useOutside(() => setOpen(false));
  const matches = ASSETS.filter((a) => a.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <div className="nx-cmd-wrap" ref={ref}>
      <div className="nx-cmd">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.7" /><path d="M20 20l-3.2-3.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
        <input value={q} placeholder={t("cmd")} aria-label={t("cmd")}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
      </div>
      {open && q.trim() ? (
        <div className="nx-cmd-results">
          {matches.map((a) => (
            <a key={a} href={`/app/market/${a}`} onClick={(e) => { e.preventDefault(); setOpen(false); setQ(""); nav(`/app/market/${a}`); }}>
              <span>{a} · Asset</span><span className="nx-badge live">LIVE</span>
            </a>
          ))}
          <div className="soon"><span>Ask NEXUS · natural-language screening</span><span className="nx-badge soon">SOON</span></div>
        </div>
      ) : null}
    </div>
  );
}

export function HeaderControls() {
  const { view, setView, theme, resolvedTheme, setTheme, locale, setLocale, t } = useExperience();
  const [tOpen, setTOpen] = useState(false);
  const [lOpen, setLOpen] = useState(false);
  const tRef = useOutside(() => setTOpen(false));
  const lRef = useOutside(() => setLOpen(false));
  const views: [ViewMode, string][] = [["simple", t("simple")], ["standard", t("standard")], ["pro", t("pro")]];
  const themes: [ThemeMode, string][] = [["system", t("sys")], ["light", t("light")], ["dark", t("dark")]];
  return (
    <div className="nx-ctrls">
      <div className="nx-seg" role="group" aria-label={t("view")}>
        {views.map(([v, label]) => (
          <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>{label}</button>
        ))}
      </div>
      <div className="nx-menu-wrap" ref={tRef}>
        <button className="nx-iconbtn" aria-haspopup="menu" aria-expanded={tOpen} aria-label={t("theme")} onClick={() => setTOpen((v) => !v)}>
          {resolvedTheme === "dark"
            ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
            : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.7" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>}
        </button>
        {tOpen ? <div className="nx-menu" role="menu">{themes.map(([m, label]) => (
          <button key={m} role="menuitemradio" aria-checked={theme === m} onClick={() => { setTheme(m); setTOpen(false); }}><span>{label}</span>{theme === m ? <span>✓</span> : null}</button>
        ))}</div> : null}
      </div>
      <div className="nx-menu-wrap" ref={lRef}>
        <button className="nx-iconbtn" aria-haspopup="menu" aria-expanded={lOpen} aria-label={t("lang")} onClick={() => setLOpen((v) => !v)}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" /><path d="M3 12h18M12 3c2.5 2.5 2.5 15.5 0 18M12 3c-2.5 2.5-2.5 15.5 0 18" stroke="currentColor" strokeWidth="1.6" /></svg>
          <span style={{ fontSize: "0.76rem" }}>{locale.split("-")[0].toUpperCase()}</span>
        </button>
        {lOpen ? <div className="nx-menu" role="menu">{LOCALES.map((l: Locale) => (
          <button key={l} role="menuitemradio" aria-checked={locale === l} onClick={() => { setLocale(l); setLOpen(false); }}><span>{LOCALE_NAMES[l]}</span>{locale === l ? <span>✓</span> : null}</button>
        ))}</div> : null}
      </div>
    </div>
  );
}
