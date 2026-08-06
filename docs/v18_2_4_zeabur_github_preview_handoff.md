# V18.2.4 — Zeabur GitHub Preview (Founder handoff)

**Production (do not change):** https://nexus-bybit-demo-val.zeabur.app/  
**Production service ID:** `69d559cb2696d526abde8cda`  
**Preview service name:** `nexus-member-preview-v18-2-1`  
**GitHub repo:** `https://github.com/sam95006/btc_auto.git`  
**Deployment branch:** `deploy/nexus-member-preview-v18-2-1`

## Zeabur UI steps (Founder)

1. Open existing NEXUS Zeabur project (`69d559b62696d526abde8cd9`).
2. **Add Service** → **GitHub** → repository **sam95006/btc_auto**.
3. Branch: **`deploy/nexus-member-preview-v18-2-1`** (not production branch).
4. Service name: **`nexus-member-preview-v18-2-1`**.
5. Match production topology (same as working `nexus-bybit-demo-val` service):
   - **Root directory:** repository root (`.`)
   - **Dockerfile:** `Dockerfile` (repo root)
   - **Start:** `gunicorn -c gunicorn.conf.py app:app` (image default)
6. **Build-time environment** (required before `npm run build` in build command):

| Variable | Value |
|----------|--------|
| `VITE_MEMBER_SURFACE_V18_2_1` | `true` |
| `VITE_PREVIEW_ENTITLEMENT_REVIEW` | `true` |
| `NEXUS_DEPLOYMENT_ENV` | `preview` |
| `NEXUS_PRODUCTION_PROMOTION` | `false` |
| `NEXUS_PRODUCTION_BILLING` | `false` |
| `NEXUS_MEMBER_EXECUTION` | `false` |

7. **Recommended build command** (if Zeabur allows custom build; mirror production + frontend sync):

```bash
cd frontend && npm ci && npm run build && cd .. && python tools/deploy/sync_operator_ui_into_zeabur_stage3.py
```

If production uses Dockerfile-only build without a separate npm step, add the above as **Pre-deploy** or Zeabur **Build Command** override so `static/operator_ui` contains the V18.2.1 SPA before the Docker image is built.

8. Deploy. Do **not** redeploy or reconfigure production service `69d559cb2696d526abde8cda`.

## After deploy

- Health: `GET https://<preview-domain>/health` → `operator_ui_ready: true`
- Review: `https://<preview-domain>/preview/v18_2_1/review`
- Remote validation:

```bash
python tools/deploy/validate_nexus_remote_preview.py --base-url "https://<preview-domain>"
```

## Rollback

Redeploy previous preview service image or switch branch; never replace production default surface without Founder approval.
