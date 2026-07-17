/** Event notification preferences + unread tracking (localStorage). */

import type { ScannerEvent } from "./scannerApi";

const PREF_KEY = "nexus_mi_event_prefs_v1";
const READ_KEY = "nexus_mi_event_read_v1";

export type EventPrefs = {
  version: 1;
  toast: boolean;
  sound: boolean;
  browserNotify: boolean;
};

const DEFAULT_PREFS: EventPrefs = {
  version: 1,
  toast: true,
  sound: false,
  browserNotify: false,
};

export function loadEventPrefs(): EventPrefs {
  try {
    const raw = localStorage.getItem(PREF_KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const p = JSON.parse(raw) as Partial<EventPrefs>;
    return {
      version: 1,
      toast: p.toast !== false,
      sound: p.sound === true,
      browserNotify: p.browserNotify === true,
    };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function saveEventPrefs(prefs: EventPrefs) {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify({ ...prefs, version: 1 }));
  } catch {
    /* ignore */
  }
}

export function loadReadEventIds(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as string[];
    return new Set(Array.isArray(arr) ? arr.slice(-200) : []);
  } catch {
    return new Set();
  }
}

export function markEventsRead(ids: string[]) {
  const cur = loadReadEventIds();
  ids.forEach((id) => cur.add(id));
  const arr = [...cur].slice(-200);
  try {
    localStorage.setItem(READ_KEY, JSON.stringify(arr));
  } catch {
    /* ignore */
  }
}

export function clearReadEvents() {
  try {
    localStorage.removeItem(READ_KEY);
  } catch {
    /* ignore */
  }
}

export function isHighPriorityEvent(ev: ScannerEvent): boolean {
  const t = (ev.type || "").toUpperCase();
  return (
    t.includes("NEW_TOP") ||
    t.includes("CONFIRMED") ||
    t.includes("OVEREXTENDED") ||
    t.includes("STAGE_CHANGE")
  );
}

export function eventTypeLabelZh(type: string): string {
  const t = (type || "").toUpperCase();
  if (t.includes("NEW_TOP")) return "新進榜";
  if (t.includes("RANK_UP")) return "排名上升";
  if (t.includes("OVEREXTENDED")) return "過熱警告";
  if (t.includes("COOLING")) return "條件減弱";
  if (t.includes("EXPIRED")) return "候選失效";
  if (t.includes("STAGE")) return "階段變化";
  if (t.includes("CONFLICT")) return "衝突增加";
  if (t.includes("ANOMALY")) return "市場異動";
  return "市場事件";
}
