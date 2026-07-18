/** Sector APIs — Phase 3 read-only. */

export type SectorRow = {
  id: string;
  slug: string;
  nameZhTW: string;
  nameEn: string;
  sectorState: string;
  sectorStateLabelZh: string;
  memberCount: number;
  validMarketCount: number;
  deepScanMemberCount: number;
  medianReturn24h?: number | null;
  turnoverWeightedReturn24h?: number | null;
  breadthRatio?: number | null;
  medianFundingRate?: number | null;
  medianOiChange5m?: number | null;
  longCandidateCount: number;
  shortCandidateCount: number;
  confirmedCandidateCount: number;
  overextendedCount: number;
  sampleNote?: string;
  reasons?: string[];
  freshness?: string;
  risingCount?: number;
  fallingCount?: number;
  collectingCount?: number;
  neutralCount?: number;
  turnoverContribution?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`sector_http_${res.status}`);
  return (await res.json()) as T;
}

export function fetchSectorsStatus() {
  return getJson<{
    ok: boolean;
    breadthMarketCount?: number;
    deepScanCount?: number;
    classifiedSymbolCount?: number;
    unclassifiedSymbolCount?: number;
    sectorCount?: number;
    freshness?: string;
    marketCoverageWording?: string;
  }>("/api/market/sectors/status");
}

export function fetchSectors(sort = "performance", state?: string) {
  const qs = new URLSearchParams({ sort });
  if (state) qs.set("state", state);
  return getJson<{
    ok: boolean;
    sectors: SectorRow[];
    breadthMarketCount?: number;
    deepScanCount?: number;
    classifiedSymbolCount?: number;
    unclassifiedSymbolCount?: number;
  }>(`/api/market/sectors?${qs}`);
}

export function fetchSectorDetail(id: string) {
  return getJson<{
    ok: boolean;
    sector?: SectorRow;
    insight?: string;
    error?: string;
  }>(`/api/market/sectors/${encodeURIComponent(id)}`);
}

export function fetchSectorSymbols(id: string, limit = 80) {
  return getJson<{ ok: boolean; symbols: Record<string, unknown>[]; count?: number }>(
    `/api/market/sectors/${encodeURIComponent(id)}/symbols?limit=${limit}`,
  );
}
