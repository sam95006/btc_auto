/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MEMBER_SURFACE_V18_2_1?: string;
  readonly VITE_PREVIEW_ENTITLEMENT_REVIEW?: string;
  readonly VITE_BUILD_COMMIT?: string;
  readonly VITE_MEMBER_TIER_PREVIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
