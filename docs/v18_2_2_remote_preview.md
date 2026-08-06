# V18.2.2 Remote member preview + entitlement review

## Review route

- **Path:** `/preview/v18_2_1/review` → `/review?member_surface_v18_2_1=1`
- **Build flags (preview service only):**
  - `VITE_MEMBER_SURFACE_V18_2_1=true`
  - `VITE_PREVIEW_ENTITLEMENT_REVIEW=true`
  - Optional: `VITE_BUILD_COMMIT=<git rev-parse HEAD>`

`preview_entitlement_override_available_in_prod` is **false** — production default build must not expose plan override via query string.

## Local build & preview

```powershell
cd frontend
$env:VITE_MEMBER_SURFACE_V18_2_1="true"
$env:VITE_PREVIEW_ENTITLEMENT_REVIEW="true"
$env:VITE_BUILD_COMMIT=(git -C .. rev-parse HEAD)
npm run build
npx vite preview --host 127.0.0.1 --port 4173
```

Open: `http://127.0.0.1:4173/preview/v18_2_1/review`

## Separate Zeabur preview service (do NOT redeploy production SERVICE_ID)

Production unchanged: https://nexus-bybit-demo-val.zeabur.app/

1. Create or select service **nexus-member-preview-v18-2-1** in project `69d559b62696d526abde8cd9`.
2. Deploy branch `feature/nexus-public-v18-2-1-actual-panel` at commit `PUBLIC_V18_2_2_REMOTE_PREVIEW_HEAD`.
3. Set env on **preview service only**:
   - `VITE_MEMBER_SURFACE_V18_2_1=true`
   - `VITE_PREVIEW_ENTITLEMENT_REVIEW=true`
4. Build artifact: `cd frontend && npm run build` (with env above at build time).
5. Health: `GET /health` (expect console_assets / app ok per existing deploy).
6. Rollback: redeploy previous preview image or unset review flag and rebuild.

Reference: `tools/deploy/zeabur_redeploy.sh` — override `ZEABUR_SERVICE_ID` to the **preview** service id, never `69d559cb2696d526abde8cda` for experimental flags.

## Visual evidence (coordinator path)

```powershell
cd frontend
node e2e/v18_2_2_review_visual.mjs
```

Output: `D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_2_remote_preview\` (PNG + manifest JSON, not in git).
