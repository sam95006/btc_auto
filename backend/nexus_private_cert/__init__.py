"""PRIVATE-ENV-2R server-side read-only certification.

This package runs INSIDE the private validation runtime
(`nexus-bybit-demo-learning-validation`) and uses the service's own
environment-held credentials (AI provider keys, Bybit Demo key/secret,
PostgreSQL DSN) to produce a strictly redacted PASS/FAIL certification.

Hard guarantees:
- READ-ONLY: no order submit / cancel / amend / close / position or leverage
  mutation / transfer / withdrawal is reachable from this path.
- Fail-closed: certification hard-fails unless the demo-only safety flags hold
  (BYBIT_DEMO=true, MAINNET/REAL_MONEY/EXCHANGE_WRITE/DEMO_AUTONOMOUS_ENABLED/
  AUTONOMOUS_SEND=false).
- Redacted: no API key, secret, token, DSN, authorization header, or raw
  provider payload ever appears in the response.
"""

from backend.nexus_private_cert.certifier import run_certification  # noqa: F401
from backend.nexus_private_cert.safety import safety_gate  # noqa: F401
