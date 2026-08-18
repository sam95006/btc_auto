#!/bin/sh
# Shared P1 validation runtime: disarmed flags, unique evidence, reject empty JSON.

p1_export_disarmed_flags() {
  export MAINNET=false
  export REAL_MONEY=false
  export DEMO_AUTONOMOUS_ENABLED=false
  export AUTONOMOUS_SEND=false
  export EXCHANGE_WRITE=false
}

p1_unique_evidence_path() {
  kind="$1"
  echo "/tmp/nexus_demo_validation/${kind}_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}.json"
}

p1_reject_empty_json() {
  file="$1"
  if [ ! -s "$file" ]; then
    echo "authoritative_evidence_empty=true"
    return 1
  fi
  python -c "import json,sys; data=json.load(open(sys.argv[1],encoding='utf-8')); assert isinstance(data, dict)" "$file"
}
