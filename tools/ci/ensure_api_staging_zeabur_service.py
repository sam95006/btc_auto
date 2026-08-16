#!/usr/bin/env python3
"""Resolve the existing Zeabur API staging service; print its id only.

Never prints API tokens, DSNs, or secrets. Does not touch member-preview, Stage3,
or Demo Validation service ids.
"""
from __future__ import annotations

import os
SERVICE_NAME = "nexus-api-staging"
EXISTING_API_STAGING_SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
FORBIDDEN_MEMBER_PREVIEW = "69d559cb2696d526abde8cda"
FORBIDDEN_STAGE3 = "6a3b81652fdef84a45a2a553"
FORBIDDEN_VALIDATION = "6a69ad539949111176cefe63"


def main() -> int:
    preset = os.environ.get("PRESET_SERVICE_ID", "").strip() or EXISTING_API_STAGING_SERVICE_ID
    if preset in {FORBIDDEN_MEMBER_PREVIEW, FORBIDDEN_STAGE3, FORBIDDEN_VALIDATION}:
        print("BLOCKED_FORBIDDEN_SERVICE_ID", file=sys.stderr)
        return 3
    if preset != EXISTING_API_STAGING_SERVICE_ID:
        print("BLOCKED_UNEXPECTED_API_STAGING_SERVICE_ID", file=sys.stderr)
        return 3
    print(preset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
