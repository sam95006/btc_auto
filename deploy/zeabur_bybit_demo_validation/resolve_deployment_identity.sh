#!/bin/sh
# Resolve the immutable source commit for the Validation container.
# Only a full 40-hex Git SHA is accepted; missing/invalid values fail closed.
set -eu

is_full_git_sha() {
  printf '%s' "${1:-}" | grep -Eq '^[0-9a-f]{40}$'
}

clean_value() {
  printf '%s' "${1:-}" | tr -d ' \t\r\n' | tr 'A-F' 'a-f'
}

resolve_deployment_identity() {
  for file in ./DEPLOYMENT_COMMIT ./SOURCE_COMMIT /app/DEPLOYMENT_COMMIT /app/SOURCE_COMMIT; do
    if [ -s "$file" ]; then
      val=$(clean_value "$(cat "$file")")
      if is_full_git_sha "$val"; then
        printf '%s' "$val"
        return 0
      fi
    fi
  done

  for key in \
    NEXUS_DEPLOYMENT_COMMIT \
    NEXUS_SOURCE_COMMIT \
    GITHUB_SHA \
    ZEABUR_GIT_COMMIT_SHA \
    ZEABUR_ENV_GITHUB_SHA \
    ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA \
    SOURCE_COMMIT
  do
    # shellcheck disable=SC2086
    eval "raw=\${$key-}"
    val=$(clean_value "$raw")
    if is_full_git_sha "$val"; then
      printf '%s' "$val"
      return 0
    fi
  done
  return 1
}

write_deployment_identity_files() {
  if sha=$(resolve_deployment_identity); then
    printf '%s\n' "$sha" > ./DEPLOYMENT_COMMIT
    printf '%s\n' "$sha" > ./SOURCE_COMMIT
    return 0
  fi
  : > ./DEPLOYMENT_COMMIT
  : > ./SOURCE_COMMIT
  return 0
}

case "${1:-print}" in
  print)
    resolve_deployment_identity
    ;;
  write)
    write_deployment_identity_files
    ;;
  *)
    echo "usage: $0 [print|write]" >&2
    exit 2
    ;;
esac
