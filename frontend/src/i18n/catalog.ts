import { en } from "./messages/en";
import { zhTW, type MessageKey } from "./messages/zh-TW";

export type LocaleCode = "zh-TW" | "en";

/** Product default: Traditional Chinese (Taiwan). English is ready via switcher. */
export const DEFAULT_LOCALE: LocaleCode = "zh-TW";

export const LOCALE_STORAGE_KEY = "nexus.member.locale";

const CATALOGS: Record<LocaleCode, Record<MessageKey, string>> = {
  "zh-TW": zhTW,
  en,
};

export function isLocaleCode(value: string | null | undefined): value is LocaleCode {
  return value === "zh-TW" || value === "en";
}

export function resolveLocale(preferred?: string | null): LocaleCode {
  if (isLocaleCode(preferred)) return preferred;
  return DEFAULT_LOCALE;
}

export function translate(locale: LocaleCode, key: MessageKey): string {
  const catalog = CATALOGS[locale] ?? CATALOGS[DEFAULT_LOCALE];
  return catalog[key] ?? CATALOGS[DEFAULT_LOCALE][key] ?? key;
}

export function listMessageKeys(): MessageKey[] {
  return Object.keys(zhTW) as MessageKey[];
}

export function assertCatalogParity(): { ok: true } | { ok: false; missingInEn: string[] } {
  const missingInEn = listMessageKeys().filter((k) => !(k in en) || !en[k]);
  if (missingInEn.length) return { ok: false, missingInEn };
  return { ok: true };
}

export type { MessageKey };
