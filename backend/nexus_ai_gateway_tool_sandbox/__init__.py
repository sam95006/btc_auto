"""V18-E AI Gateway and Tool Sandbox.

Unified typed gateway over:
  LOCAL | OPENAI_COMPATIBLE | GROQ | SAMBANOVA |
  OTHER_APPROVED_PROVIDER | DETERMINISTIC_FALLBACK

Tool allow-list only (read paths). Banned: exchange write, account/wallet,
API secrets, risk/leverage override, Lesson activation, strategy/code deploy.

Routing:
  simple → deterministic / low-cost
  candidate interpretation → primary
  major contradictions → critic
  all providers down → WAIT/ABSTAIN with PROVIDER_CAPACITY_BLOCKED +
    CONTINUE_WITHOUT_AI (never freeze pipeline, never busy-loop)
"""
from __future__ import annotations

from backend.nexus_ai_gateway_tool_sandbox.adapters import (
    build_default_adapters,
    provider_status_matrix,
)
from backend.nexus_ai_gateway_tool_sandbox.constants import (
    ALLOWED_TOOLS,
    BANNED_TOOLS,
    CAPACITY_STATUS,
    PIPELINE_CONTINUE,
    PROVIDER_IDS,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import (
    GatewayRequest,
    GatewayResponse,
    ToolCallRequest,
)
from backend.nexus_ai_gateway_tool_sandbox.fixtures import fixture_catalog, run_fixture
from backend.nexus_ai_gateway_tool_sandbox.gateway import UnifiedAIGateway
from backend.nexus_ai_gateway_tool_sandbox.hard_bans import hard_ban_probe_matrix
from backend.nexus_ai_gateway_tool_sandbox.tools import ToolSandbox

__all__ = [
    "ALLOWED_TOOLS",
    "BANNED_TOOLS",
    "CAPACITY_STATUS",
    "PIPELINE_CONTINUE",
    "PROVIDER_IDS",
    "GatewayRequest",
    "GatewayResponse",
    "ToolCallRequest",
    "ToolSandbox",
    "UnifiedAIGateway",
    "build_default_adapters",
    "fixture_catalog",
    "hard_ban_probe_matrix",
    "provider_status_matrix",
    "run_fixture",
]
