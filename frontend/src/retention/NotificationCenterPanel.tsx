import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { RETENTION_ALERT_LABELS, type RetentionNotification } from "./alertEventTypes";
import { AuthRequiredBlocker } from "./AuthRequiredBlocker";
import { fetchNotifications, isAuthRequired, markNotificationRead } from "./retentionApi";

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

/** Compact server-backed notification timeline (in-app). */
export function NotificationCenterPanel() {
  const [authRequired, setAuthRequired] = useState(false);
  const [items, setItems] = useState<RetentionNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    const { res, body } = await fetchNotifications(40);
    if (res.status === 401 || isAuthRequired(body)) {
      setAuthRequired(true);
      setItems([]);
      setUnread(0);
      return;
    }
    setAuthRequired(false);
    setItems((body.items as RetentionNotification[]) || []);
    setUnread(Number(body.unread) || 0);
  };

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        await reload();
      } finally {
        if (alive) setLoading(false);
      }
    })();
    const id = window.setInterval(() => void reload(), 45_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (loading) {
    return <div className="mp2-skeleton" style={{ height: 48 }} aria-busy="true" />;
  }
  if (authRequired) {
    return <AuthRequiredBlocker title="通知中心需要登入" />;
  }

  return (
    <section data-testid="server-notification-center" aria-label="Notification center">
      <header style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h2 className="mp2-page-title" style={{ fontSize: "1.05rem" }}>
            通知
          </h2>
          <p className="mp2-page-sub">伺服器時間軸 · 未讀 {unread}</p>
        </div>
        <Link to="/alerts" className="mp2-btn mp2-btn-ghost">
          警報頁
        </Link>
      </header>
      {items.length === 0 ? (
        <p className="muted" style={{ marginTop: 12 }}>
          尚無通知
        </p>
      ) : (
        <div className="mp2-notify-timeline" style={{ marginTop: 12 }}>
          {items.map((n) => (
            <article
              key={n.id}
              className={`mp2-alert-row${n.read ? "" : " unread"}`}
              onClick={() => {
                if (!n.read) {
                  void markNotificationRead(n.id).then(() => void reload());
                }
              }}
            >
              <span className="time">{agoLabel(n.ts)}</span>
              <span className="kind">
                {(RETENTION_ALERT_LABELS as Record<string, string>)[n.type] || n.type}
              </span>
              <div>
                <Link to={n.link || "/alerts"}>
                  <strong>{n.headline}</strong>
                </Link>
                <div className="muted" style={{ fontSize: "0.75rem", marginTop: 2 }}>
                  {n.severity} · {n.symbol || "—"} · {n.source}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
