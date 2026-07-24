/**
 * Notification preference persistence contract (Product 7.2).
 *
 * STORAGE_CONTRACT:
 *   scope:        LOCAL_ONLY — stored in localStorage of this browser only.
 *   sync:         NOT synced across devices. No backend.
 *   browserPush:  REQUIRES Notification.permission === "granted".
 *                 NEVER claim push is enabled without real permission.
 *   sound:        Only if user explicitly opts in AND not muted.
 *   digestOnly:   Default true (anti-spam). Real-time alerts off by default.
 *
 * NEVER set browserNotify=true without Notification API permission grant.
 * Prefer digest-only defaults to avoid notification spam.
 */

import { loadEventPrefs, saveEventPrefs, type EventPrefs } from "./eventPrefs";

export type BrowserPushPermission = "granted" | "denied" | "default" | "unsupported";

export type NotificationPrefs = EventPrefs & {
  /** Master mute — when true, no toasts even if toast=true. */
  muted: boolean;
  /** Digest-only mode (no push spam). Default true. */
  digestOnly: boolean;
  /**
   * Actual browser Notification.permission value at time of last check.
   * NOT user preference — reflects real API state.
   * Never claim push is enabled without "granted" here.
   */
  browserPushPermission: BrowserPushPermission;
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
    /* ignore quota */
  }
}

/**
 * Returns current browser Notification.permission.
 * Returns "unsupported" if Notification API is not available (SSR / old browser).
 */
export function getBrowserPushPermission(): BrowserPushPermission {
  if (typeof window === "undefined") return "unsupported";
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission as BrowserPushPermission;
}

/**
 * Returns true ONLY if Notification API is granted.
 * Never return true based on stored preference alone.
 */
export function isBrowserPushGranted(): boolean {
  return getBrowserPushPermission() === "granted";
}

export function loadNotificationPrefs(): NotificationPrefs {
  const base = loadEventPrefs();
  const extra = loadExtra();
  const permission = getBrowserPushPermission();
  return {
    ...base,
    sound: base.sound === true,
    // Only set browserNotify true if BOTH user opted in AND permission is granted.
    browserNotify: base.browserNotify === true && permission === "granted",
    muted: extra.muted === true,
    digestOnly: extra.digestOnly !== false, // default true
    browserPushPermission: permission,
  };
}

export function saveNotificationPrefs(prefs: NotificationPrefs) {
  const permission = getBrowserPushPermission();
  // Never save browserNotify=true if permission is not granted.
  const safeBrowserNotify = prefs.browserNotify === true && permission === "granted";
  saveEventPrefs({
    version: 1,
    toast: prefs.toast && !prefs.muted,
    sound: prefs.sound === true && !prefs.muted,
    browserNotify: safeBrowserNotify,
  });
  saveExtra({ muted: prefs.muted === true, digestOnly: prefs.digestOnly !== false });
}

export function shouldEmitNotification(prefs: NotificationPrefs = loadNotificationPrefs()): boolean {
  if (prefs.muted) return false;
  if (prefs.digestOnly) return false; // stub: no realtime spam
  return prefs.toast === true;
}

/**
 * Returns a human-readable disclosure for UI panels.
 */
export function notificationPrefsDisclosure(): string {
  const perm = getBrowserPushPermission();
  const permLabel =
    perm === "granted"
      ? "已授權"
      : perm === "denied"
        ? "已拒絕（需在瀏覽器手動解除）"
        : perm === "unsupported"
          ? "瀏覽器不支援"
          : "尚未詢問";
  return `通知偏好僅存於本瀏覽器 localStorage。瀏覽器推播許可：${permLabel}。不跨裝置，不上傳雲端。`;
}
