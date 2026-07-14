import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { DocCategory, DocSummaryFilterState, GateStatusLabel } from "../demo/docSummaries";
import {
  DOC_CATEGORIES,
  EMPTY_DOC_SUMMARY_FILTER,
  GATE_STATUS_OPTIONS,
} from "../demo/docSummaries";

/**
 * Sync Evidence Center filters with URL query (MVP-18).
 * Params: q · category · gateStatus · unresolved · tag
 * READ ONLY · sanitized filter state only · no backend · no /data · no localStorage secrets
 */
export function useEvidenceFilterQueryState(): [
  DocSummaryFilterState,
  (next: DocSummaryFilterState) => void,
] {
  const [params, setParams] = useSearchParams();

  const filter = useMemo((): DocSummaryFilterState => {
    const categoryRaw = params.get("category") ?? "";
    const gateRaw = params.get("gateStatus") ?? "";
    const category = (DOC_CATEGORIES as string[]).includes(categoryRaw)
      ? (categoryRaw as DocCategory)
      : "";
    const gateStatus = (GATE_STATUS_OPTIONS as string[]).includes(gateRaw)
      ? (gateRaw as GateStatusLabel)
      : "";
    const unresolved = params.get("unresolved");
    return {
      query: params.get("q") ?? "",
      category,
      gateStatus,
      unresolvedOnly: unresolved === "true" || unresolved === "1",
      tag: params.get("tag") ?? "",
    };
  }, [params]);

  const setFilter = useCallback(
    (next: DocSummaryFilterState) => {
      const sp = new URLSearchParams();
      if (next.query.trim()) sp.set("q", next.query.trim());
      if (next.category) sp.set("category", next.category);
      if (next.gateStatus) sp.set("gateStatus", next.gateStatus);
      if (next.unresolvedOnly) sp.set("unresolved", "true");
      if (next.tag.trim()) sp.set("tag", next.tag.trim());
      setParams(sp, { replace: true });
    },
    [setParams],
  );

  return [filter, setFilter];
}

export { EMPTY_DOC_SUMMARY_FILTER };
