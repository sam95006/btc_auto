/**
 * Notification preference foundation — preference UI stub, no spam defaults.
 * Extends event prefs shape; browser/sound off by default.
 */

import { loadEventPrefs, saveEventPrefs, type EventPrefs } from "./eventPrefs";

export type NotificationPrefs = EventPrefs & {
  /** Master mute — when true, no toasts even if toast=true. */
  muted: boolean;
  /** Digest-only mode stub (no push spam). */
  digestOnly: boolean;
};

const EXTRA_KEY = "nexus_mi_notification_prefs_v1";

type Extra = { muted?: boolean; digestOnly?: boolean };

function loadExtra(): Extra {
  try {
    const raw = localStorage.getItem(EXTRA_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Extra;
  } catch {
    return {};
  }
}

function saveExtra(extra: Extra) {
  try {
    localStorage.setItem(EXTRA_KEY, JSON.stringify(extra));
  } catch {
    /* ignore */
  }
}

export function loadNotificationPrefs(): NotificationPrefs {
  const base = loadEventPrefs();
  const extra = loadExtra();
  return {
    ...base,
    sound: base.sound === true,
    browserNotify: base.browserNotify === true,
    muted: extra.muted === true,
    digestOnly: extra.digestOnly !== false, // default true
  };
}

export function saveNotificationPrefs(prefs: NotificationPrefs) {
  saveEventPrefs({
    version: 1,
    toast: prefs.toast && !prefs.muted,
    sound: prefs.sound === true && !prefs.muted,
    browserNotify: prefs.browserNotify === true && !prefs.muted,
  });
  saveExtra({ muted: prefs.muted === true, digestOnly: prefs.digestOnly !== false });
}

export function shouldEmitNotification(prefs: NotificationPrefs = loadNotificationPrefs()): boolean {
  if (prefs.muted) return false;
  if (prefs.digestOnly) return false; // stub: no realtime spam
  return prefs.toast === true;
}
