import { Link } from "react-router-dom";
import { AUTH_REQUIRED_BLOCKER } from "./retentionApi";

/** Honest auth gate — never invents identity. */
export function AuthRequiredBlocker({
  title = "需要登入",
  detail = "伺服器自選 / 通知 / 上次造訪摘要需要真實身分與工作階段。未登入時不會建立假身分。",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div
      className="mp2-auth-blocker"
      data-testid="auth-required-blocker"
      data-blocker={AUTH_REQUIRED_BLOCKER}
      role="status"
    >
      <strong>{title}</strong>
      <p className="muted" style={{ marginTop: 6 }}>
        {detail}
      </p>
      <p className="mono muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>
        {AUTH_REQUIRED_BLOCKER}
      </p>
      <div className="mp2-actions" style={{ marginTop: 12 }}>
        <Link to="/account" className="mp2-btn mp2-btn-primary">
          前往帳戶
        </Link>
        <Link to="/overview" className="mp2-btn mp2-btn-ghost">
          繼續瀏覽市場
        </Link>
      </div>
    </div>
  );
}
