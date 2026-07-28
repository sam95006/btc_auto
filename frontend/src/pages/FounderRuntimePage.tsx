import { Link } from "react-router-dom";
import { BybitDemoAutonomousCard } from "../components/BybitDemoAutonomousCard";

/**
 * Founder-only runtime observability — READ ONLY labels.
 * BybitDemoAutonomousCard moved from public overview.
 */
export function FounderRuntimePage() {
  return (
    <div className="page-stack nx-founder-runtime-w4">
      <header>
        <h1>Founder Runtime</h1>
        <p className="muted">
          私有營運觀測 · READ ONLY · 不對外公開 Demo 卡片
        </p>
        <div className="tag tag-warn">founder / runtime · shadow observability only</div>
      </header>

      <section className="nx-card" aria-label="Access note">
        <p className="muted sm">
          此頁取代公開總覽上的 Bybit Demo Autonomous 卡片。無下單、無 ARM、無 mainnet 控件。
        </p>
        <Link to="/overview">← 返回公開總覽</Link>
      </section>

      <BybitDemoAutonomousCard />

      <section className="nx-card muted sm">
        <p>相關連結：</p>
        <Link to="/provider-shadow">Provider Shadow</Link>
        {" · "}
        <Link to="/global-shadow">Global Shadow</Link>
        {" · "}
        <Link to="/evidence">Evidence</Link>
      </section>
    </div>
  );
}
