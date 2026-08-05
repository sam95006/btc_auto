import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  resolveLocale,
  translate,
  type LocaleCode,
  type MessageKey,
} from "./catalog";

type I18nContextValue = {
  locale: LocaleCode;
  setLocale: (locale: LocaleCode) => void;
  t: (key: MessageKey) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(): LocaleCode {
  try {
    return resolveLocale(localStorage.getItem(LOCALE_STORAGE_KEY));
  } catch {
    return DEFAULT_LOCALE;
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(() =>
    typeof window === "undefined" ? DEFAULT_LOCALE : readStoredLocale(),
  );

  const setLocale = useCallback((next: LocaleCode) => {
    setLocaleState(next);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      /* ignore quota / private mode */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = translate(locale, "meta.htmlLang");
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key) => translate(locale, key),
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n requires I18nProvider");
  return ctx;
}

export function useT(): (key: MessageKey) => string {
  return useI18n().t;
}
