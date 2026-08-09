/** Retention alert event types — mirror backend contract. */

export const RETENTION_ALERT_EVENT_TYPES = [
  "RADAR_NEW",
  "RADAR_UP",
  "RADAR_DOWN",
  "RADAR_OUT",
  "STATE_CHANGE",
  "ACTIVITY_ACCELERATION",
  "OI_CHANGE",
  "FUNDING_EXTREME",
  "RISK_CHANGE",
  "DATA_DEGRADED",
  "WATCHLIST_EVENT",
] as const;

export type RetentionAlertEventType = (typeof RETENTION_ALERT_EVENT_TYPES)[number];

export const RETENTION_ALERT_LABELS: Record<RetentionAlertEventType, string> = {
  RADAR_NEW: "Radar NEW",
  RADAR_UP: "Radar UP",
  RADAR_DOWN: "Radar DOWN",
  RADAR_OUT: "Radar OUT",
  STATE_CHANGE: "State change",
  ACTIVITY_ACCELERATION: "Activity ↑",
  OI_CHANGE: "OI change",
  FUNDING_EXTREME: "Funding extreme",
  RISK_CHANGE: "Risk change",
  DATA_DEGRADED: "Data degraded",
  WATCHLIST_EVENT: "Watchlist",
};

export type RetentionNotification = {
  id: string;
  ts: number;
  symbol: string;
  type: string;
  severity: string;
  headline: string;
  metric?: Record<string, unknown>;
  source: string;
  read: boolean;
  link: string;
};
