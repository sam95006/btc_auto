# Corporate Market Intelligence — static SPA runtime (CORPORATE-1)
#
# Serves ONLY the Corporate frontend build (frontend/dist/corporate). NOT the
# private trading runtime, NOT Personal, NOT Founder. No Gunicorn, no
# ResearchAutonomyService, no Bybit runner, no secrets.
#   MAINNET=false  REAL_MONEY=false  EXCHANGE_WRITE=false
FROM node:20-slim AS build
WORKDIR /src
# Public API origin baked into the static build (NO secrets). Defaults to the
# staging Core API; Zeabur injects the service's VITE_NEXUS_API_ORIGIN as this
# build arg so the deployed origin is explicit and auditable.
ARG VITE_NEXUS_API_ORIGIN=https://nexus-api-staging.zeabur.app
ENV VITE_NEXUS_API_ORIGIN=$VITE_NEXUS_API_ORIGIN
COPY . .
RUN cd frontend && npm ci
# build:corporate runs surface-boundary + no-fake-data checks and emits
# dist/corporate — Corporate surface only. Vite names the entry after its
# source HTML (corporate.html); the static server serves index.html as the SPA
# root, so normalize the entry filename to index.html (assets are referenced by
# absolute /assets/ paths, so the rename is safe).
RUN cd frontend && npm run build:corporate \
    && cp dist/corporate/corporate.html dist/corporate/index.html

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    NEXUS_CORPORATE_DIST=/app/dist/corporate \
    MAINNET=false REAL_MONEY=false EXCHANGE_WRITE=false PORT=8080
WORKDIR /app
COPY --from=build /src/frontend/dist/corporate /app/dist/corporate
COPY deploy/zeabur_corporate_v1/server.py /app/server.py
EXPOSE 8080
CMD ["python", "/app/server.py"]
