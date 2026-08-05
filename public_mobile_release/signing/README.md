# Signing abstraction

This directory defines **how** signing materials are referenced — not the materials themselves.

## Rules

1. Never commit keystores, `.p12`, provisioning profiles, or Play service-account JSON.
2. CI mounts secrets into ephemeral paths; wipe after job.
3. `publish_to_stores` remains `false` for PUB-L.
4. Local debug signing is allowed; release upload is banned without Founder + legal gates outside this lane.
