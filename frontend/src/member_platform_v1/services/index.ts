/**
 * Service re-exports. Member state and the canonical commercial catalog are served
 * exclusively by the backend (stagingApi / usePersonalCatalog) — the old static
 * PRODUCT_CATALOG that duplicated pricing here was removed in NEXUS-EXPERIENCE-1B.1.
 */
export {
  STAGING_API_ORIGIN,
  checkEntitlement,
  getLiveMarketSnapshot,
  getOrganizationPermissions,
  getStagingApiStatus,
} from "./stagingApi";
