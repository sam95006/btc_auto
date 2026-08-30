# Personal Market Intelligence — static SPA runtime (PERSONAL-2)
#
# This image serves ONLY the Personal frontend build artifact
# (frontend/dist/personal). It is deliberately NOT the legacy unified root
# Dockerfile: it does NOT run Gunicorn, ResearchAutonomyService, the Bybit
# runner, a trading worker, or any Founder/private runtime. The Personal web
# surface and the private trading runtime are separate products.
#
# Permanent safety posture (frontend artifact carries no execution authority):
#   MAINNET=false  REAL_MONEY=false  EXCHANGE_WRITE=false

# ---- build stage: produce the Personal-only artifact --------------------
FROM node:20-slim AS build
WORKDIR /src
# The whole repo is the build context: build:personal runs repo-root boundary
# checks (check_frontend_runtime_boundary reads deploy/**, etc.) and the
# frontend package.json has a local file: tarball dependency, so the build
# stage needs the full source tree. This stage is discarded — only
# dist/personal is copied into the runtime image below, so no backend/trading
# code ships in the served artifact.
COPY . .
RUN cd frontend && npm ci
# build:personal runs the surface-boundary + frontend-runtime-boundary checks
# and emits dist/personal (index.html + assets/) — Personal surface only.
RUN cd frontend && npm run build:personal

# ---- runtime stage: tiny static SPA server ------------------------------
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXUS_PERSONAL_DIST=/app/dist/personal \
    MAINNET=false \
    REAL_MONEY=false \
    EXCHANGE_WRITE=false \
    PORT=8080
WORKDIR /app
# The artifact ROOT is dist/personal itself (contains index.html + assets/).
COPY --from=build /src/frontend/dist/personal /app/dist/personal
COPY deploy/zeabur_personal_v1/server.py /app/server.py
EXPOSE 8080
# Fails closed at startup if the artifact root is invalid (root-404 guard).
CMD ["python", "/app/server.py"]
