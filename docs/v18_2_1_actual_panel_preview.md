# V18.2.1 Actual Panel — preview & rollback

## Feature flag

- **Name:** `member_surface_v18_2_1`
- **Env (build-time):** `VITE_MEMBER_SURFACE_V18_2_1=true`
- **Query (runtime):** `?member_surface_v18_2_1=1`
- **Preview path:** `/preview/v18_2_1/<route>` → redirects to `/<route>?member_surface_v18_2_1=1`

When the flag is **off**, production serves the **legacy Zeabur** Wave 4 shell (`LegacyMarketIntelligenceApp`).

When **on**, serves `ActualPanelV1821App` (總覽 / 機會 / 掃描器 / 警報 / 情報 IA + entitlements).

## Local preview

```bash
cd frontend
npm run build
VITE_MEMBER_SURFACE_V18_2_1=true npx vite preview --host 127.0.0.1 --port 4173
```

Open: `http://127.0.0.1:4173/opportunities?member_surface_v18_2_1=1`

## V18.2.2 membership review (preview build)

Requires `VITE_PREVIEW_ENTITLEMENT_REVIEW=true` in addition to member surface flag. See [v18_2_2_remote_preview.md](./v18_2_2_remote_preview.md).

- **Route:** `/preview/v18_2_1/review`

## Zeabur rollback

1. Unset `VITE_MEMBER_SURFACE_V18_2_1` (or set to `false`) in service env.
2. Redeploy previous image / commit (stable tip without flag).
3. Verify `/opportunities` title remains **NEXUS — Live Market Intelligence** on legacy shell.

## Deploy (agent env may lack Zeabur token)

1. Push branch `feature/nexus-public-v18-2-1-actual-panel`.
2. Set env **only on a staging/preview service** first: `VITE_MEMBER_SURFACE_V18_2_1=true`.
3. Run `npm run build` in `frontend/`; artifact is `frontend/dist/`.
4. Deploy via existing `nexus_deploy_zeabur_on_main.yml` or `zeabur deploy` with secrets.
