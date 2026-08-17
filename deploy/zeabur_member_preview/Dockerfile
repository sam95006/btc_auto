# nexus-member-preview-v18-2-1: member SPA only.
# This image has a deliberate two-stage boundary: Node builds frontend/ and the
# final image contains only static assets plus the minimal SPA HTTP server.
FROM node:20-bookworm-slim AS build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/lightweight-charts-5.2.0.tgz ./
RUN npm ci

COPY frontend/ ./
# The boundary checker resolves the repository root as /build and verifies
# these two static-deployment files. They exist only in the build stage.
COPY deploy/zeabur_member_preview/Dockerfile \
     /build/deploy/zeabur_member_preview/Dockerfile
COPY deploy/zeabur_member_preview_v18_2_1/server.py \
     /build/deploy/zeabur_member_preview_v18_2_1/server.py
# Zeabur exposes this build-phase value for Git-backed services.  The build
# script also supports GITHUB_SHA for remote CI and a safe local fallback.
ARG ZEABUR_GIT_COMMIT_SHA=""
ENV ZEABUR_GIT_COMMIT_SHA=${ZEABUR_GIT_COMMIT_SHA}
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app
COPY --from=build /build/frontend/dist /app/dist
COPY deploy/zeabur_member_preview_v18_2_1/server.py /app/server.py

ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8080

# Static SPA server only.  No backend, runtime, supervisor, or worker exists
# in this final image.
CMD ["python", "/app/server.py"]
