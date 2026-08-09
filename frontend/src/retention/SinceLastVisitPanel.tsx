import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { AuthRequiredBlocker } from "./AuthRequiredBlocker";
import { fetchSinceLastVisit, isAuthRequired } from "./retentionApi";
import type { RetentionNotification } from "./alertEventTypes";

/** Since Last Visit — AUTH_REQUIRED_BLOCKER without real session. */
export function SinceLastVisitPanel() {
  const [authRequired, setAuthRequired] = useState(false);
  const [items, setItems] = useState<RetentionNotification[]>([]);
  const [prev, setPrev] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const { res, body } = await fetchSinceLastVisit();
        if (!alive) return;
        if (res.status === 401 || isAuthRequired(body)) {
          setAuthRequired(true);
          return;
        }
        setPrev(body.previous_visit_at ?? null);
        setItems((body.notifications_since as RetentionNotification[]) || []);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return null;
  if (authRequired) {
    return (
      <AuthRequiredBlocker
        title="Since Last Visit 需要登入"
        detail="沒有真實身分時不會偽造造訪摘要。"
      />
    );
  }

  return (
    <section data-testid="since-last-visit" style={{ marginTop: 16 }}>
      <h2 className="mp2-page-title" style={{ fontSize: "1.05rem" }}>
        自上次造訪
      </h2>
      <p className="mp2-page-sub">
        {prev ? `上次 ${new Date(prev).toLocaleString()}` : "這是此工作階段的首次造訪記錄"}
      </p>
      {items.length === 0 ? (
        <p className="muted">沒有新通知</p>
      ) : (
        <ul>
          {items.slice(0, 8).map((n) => (
            <li key={n.id}>
              <Link to={n.link || "/alerts"}>{n.headline}</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
