# Corporate Market Intelligence — static SPA runtime (CORPORATE-1)
#
# Serves ONLY the Corporate frontend build (frontend/dist/corporate). NOT the
# private trading runtime, NOT Personal, NOT Founder. No Gunicorn, no
# ResearchAutonomyService, no Bybit runner, no secrets.
#   MAINNET=false  REAL_MONEY=false  EXCHANGE_WRITE=false
FROM node:20-slim AS build
WORKDIR /src
COPY . .
RUN cd frontend && npm ci
# build:corporate runs surface-boundary + no-fake-data checks and emits
# dist/corporate (index.html + assets/) — Corporate surface only.
RUN cd frontend && npm run build:corporate

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    NEXUS_CORPORATE_DIST=/app/dist/corporate \
    MAINNET=false REAL_MONEY=false EXCHANGE_WRITE=false PORT=8080
WORKDIR /app
COPY --from=build /src/frontend/dist/corporate /app/dist/corporate
COPY deploy/zeabur_corporate_v1/server.py /app/server.py
EXPOSE 8080
CMD ["python", "/app/server.py"]
