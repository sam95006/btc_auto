#!/bin/sh
# POSIX baked-identity probe for Run #8. No Bash substring expansion.
set -e
APP_ROOT=${APP_ROOT:-/app}
EXPECTED=${EXPECTED:-}
BAKED=$(tr -d '\r\n' < "$APP_ROOT/DEPLOYMENT_COMMIT")
SOURCE=$(tr -d '\r\n' < "$APP_ROOT/SOURCE_COMMIT")
test -n "$EXPECTED"
test -n "$BAKED"
test -n "$SOURCE"
test "$BAKED" = "$EXPECTED"
test "$SOURCE" = "$EXPECTED"
test "$BAKED" = "$SOURCE"
EXPECTED12=$(printf '%s' "$EXPECTED" | cut -c1-12)
BAKED12=$(printf '%s' "$BAKED" | cut -c1-12)
SOURCE12=$(printf '%s' "$SOURCE" | cut -c1-12)
echo "expected_sha_prefix=$EXPECTED12"
echo "baked_sha_prefix=$BAKED12"
echo "source_sha_prefix=$SOURCE12"
echo "P1_RUN8_BAKED_IDENTITY_PASS=true"
