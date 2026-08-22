#!/usr/bin/env bash
# P2 migration only — builds pinned upstream zeabur/cli with deployment_id patch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIN_FILE="${ROOT}/deploy/zeabur_p2_migration_cli/PINNED_UPSTREAM_COMMIT"
PATCH_FILE="${ROOT}/deploy/zeabur_p2_migration_cli/patches/001-deploy-emit-deployment-id.patch"
OUT_BIN="${P2_ZEABUR_CLI_OUT:-/usr/local/bin/zeabur}"
WORKDIR="${P2_ZEABUR_CLI_BUILD_DIR:-/tmp/zeabur-cli-p2-build}"

PIN="$(tr -d ' \r\n' < "${PIN_FILE}")"
test -n "${PIN}"
test -f "${PATCH_FILE}"

rm -rf "${WORKDIR}"
git clone --filter=blob:none --no-checkout https://github.com/zeabur/cli.git "${WORKDIR}"
(
  cd "${WORKDIR}"
  git fetch --depth 1 origin "${PIN}"
  git checkout "${PIN}"
  git apply --check "${PATCH_FILE}"
  git apply "${PATCH_FILE}"
  go build -o "${OUT_BIN}" ./cmd/zeabur
)

echo "P2_PINNED_ZEABUR_CLI_IMPLEMENTED=true"
echo "P2_ZEABUR_PINNED_UPSTREAM_COMMIT=${PIN}"
echo "P2_ZEABUR_DEPLOYMENT_ID_DIRECT_FROM_UPLOAD=true"
"${OUT_BIN}" version 2>/dev/null || true
