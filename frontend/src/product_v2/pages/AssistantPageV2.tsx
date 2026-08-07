import { useEffect, useState } from "react";
import { ProductV2AiDrawer, openProductV2Ai } from "../ProductV2AiDrawer";

/**
 * Product V2 NEX AI full page — mirrors drawer analysis, no orb/mascot.
 */
export function AssistantPageV2() {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    openProductV2Ai();
  }, []);

  return (
    <div data-testid="product-v2-assistant" data-nexus-product-generation="2">
      <header>
        <h1 className="mp2-page-title">NEX AI</h1>
        <p className="mp2-page-sub">情境分析 · 規則引擎 · 非投資建議</p>
      </header>
      <p style={{ marginTop: 16, maxWidth: 48 * 16, color: "var(--mp2-ink-secondary)" }}>
        使用頂部「分析」開啟右側抽屜，依目前頁面提供情境提示。無 LLM 時只輸出規則摘要，不捏造。
      </p>
      <div className="mp2-actions">
        <button type="button" className="mp2-btn mp2-btn-primary" onClick={() => setOpen(true)}>
          開啟分析抽屜
        </button>
      </div>
      <ProductV2AiDrawer open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
