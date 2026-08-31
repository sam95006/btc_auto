import type { ReactNode } from "react";
import type { LoadState } from "../hooks/useCorporate";

/** Renders explicit backend-driven states. Never shows fabricated numbers. */
export function DataState<T>({
  state,
  children,
  label = "資料",
}: {
  state: LoadState<T>;
  children: (data: T) => ReactNode;
  label?: string;
}) {
  if (state.status === "LOADING")
    return <div className="corp-state corp-state-loading" role="status" aria-busy="true">載入{label}中…</div>;
  if (state.status === "UNAVAILABLE")
    return <div className="corp-state corp-state-unavailable" role="status" data-testid="state-unavailable">目前{label}無法取得（unavailable）。</div>;
  if (state.status === "ERROR")
    return <div className="corp-state corp-state-error" role="alert">載入{label}時發生錯誤。</div>;
  return <>{children(state.data)}</>;
}

export function Provenance({ source, updatedAt, freshness }: { source?: string; updatedAt?: string; freshness?: string }) {
  if (!source && !updatedAt && !freshness) return null;
  const stale = freshness === "STALE" || freshness === "DATA_DELAYED";
  return (
    <p className="corp-provenance" data-testid="provenance">
      來源 {source || "—"}
      {updatedAt ? ` · 更新 ${updatedAt}` : ""}
      {freshness ? <span className={`corp-fresh ${stale ? "is-stale" : "is-fresh"}`}> · {stale ? "延遲" : "即時"}</span> : null}
    </p>
  );
}
