from __future__ import annotations

import importlib.util
import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/api_staging_readonly_diagnostic.yml")
HELPER = Path("tools/ci/zeabur_readonly_diagnostic.py")

EXPECTED_SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
EXPECTED_ENV_ID = "69d559b6474db8a99d6dd6bf"
EXPECTED_DOMAIN = "nexus-api-staging.zeabur.app"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _load_helper():
    spec = importlib.util.spec_from_file_location("zeabur_readonly_diagnostic", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _evidence(module, service_path, domain_path, deployment_path):
    lines, ok = module.analyze(str(service_path), str(domain_path), str(deployment_path))
    out = {}
    for line in lines:
        key, _, value = line.partition("=")
        out[key] = value
    return out, ok


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# Workflow structural safety
# --------------------------------------------------------------------------

def test_workflow_contains_no_mutating_zeabur_commands() -> None:
    source = _workflow()
    assert re.search(r"zeabur\s+deploy(?!ment)", source) is None
    assert re.search(r"service\s+restart", source) is None
    assert re.search(r"variable\s+(update|create|delete)", source) is None
    assert re.search(r"service\s+(create|delete)", source) is None
    assert re.search(r"domain\s+(create|delete)", source) is None
    assert re.search(r"service\s+exec", source) is None
    assert "staging_e2e" not in source


def test_workflow_only_uses_allowed_read_only_zeabur_commands() -> None:
    source = _workflow()
    assert "zeabur auth login" in source
    assert "zeabur service get" in source
    assert "zeabur domain list" in source
    assert "zeabur deployment list" in source


def test_workflow_exact_service_and_environment_ids() -> None:
    source = _workflow()
    assert f"API_STAGING_SERVICE_ID: {EXPECTED_SERVICE_ID}" in source
    assert f"ZEABUR_ENV_ID: {EXPECTED_ENV_ID}" in source


def test_workflow_confirmation_guard_and_read_only_permissions() -> None:
    source = _workflow()
    assert "READ_NEXUS_API_STAGING" in source
    assert 'if [ "${{ github.event.inputs.confirm }}" != "READ_NEXUS_API_STAGING" ]; then' in source
    assert "permissions:" in source
    assert "contents: read" in source
    assert "write" not in source.lower()


def test_workflow_does_not_upload_raw_zeabur_json() -> None:
    source = _workflow()
    assert "upload-artifact" not in source
    assert "RAW_ZEABUR_JSON_UPLOADED=no" in source


def test_workflow_captures_query_exit_codes_and_fails_closed() -> None:
    source = _workflow()
    # No silent "|| true" swallowing of Zeabur query failures.
    assert "|| true" not in source
    assert "SERVICE_QUERY_RC=$?" in source
    assert "DOMAIN_QUERY_RC=$?" in source
    assert "DEPLOYMENT_QUERY_RC=$?" in source
    assert "READ_ONLY_DIAGNOSTIC_FAILED_CLOSED=yes" in source
    # stdout JSON kept separate from stderr.
    assert "2> /tmp/diag-service.err" in source


# --------------------------------------------------------------------------
# Parser behaviour: bare hostname vs https hostname
# --------------------------------------------------------------------------

def test_domain_parser_supports_bare_hostname(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SERVICE_QUERY_RC", raising=False)
    module = _load_helper()
    svc = _write(tmp_path, "svc.json",
                 '{"id":"%s","name":"nexus-api-staging","environmentID":"%s"}'
                 % (EXPECTED_SERVICE_ID, EXPECTED_ENV_ID))
    dom = _write(tmp_path, "dom.json",
                 '{"domains":[{"domain":"nexus-api-staging.zeabur.app","status":"CREATED"}]}')
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True
    assert ev["DOMAIN_FOUND"] == "yes"
    assert ev["DOMAIN_HOSTNAME"] == EXPECTED_DOMAIN
    assert ev["DOMAIN_VALUE_HAS_SCHEME"] == "no"
    assert ev["DOMAIN_PARSER_HTTPS_ASSUMPTION_CONFIRMED_WRONG"] == "yes"
    assert ev["DOMAIN_BINDING_PROVEN"] == "yes"


def test_domain_parser_supports_https_hostname(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json",
                 '{"id":"%s","name":"nexus-api-staging"}' % EXPECTED_SERVICE_ID)
    dom = _write(tmp_path, "dom.json",
                 '{"domains":[{"url":"https://nexus-api-staging.zeabur.app"}]}')
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True
    assert ev["DOMAIN_VALUE_HAS_SCHEME"] == "yes"
    assert ev["DOMAIN_PARSER_HTTPS_ASSUMPTION_CONFIRMED_WRONG"] == "no"


def test_domain_never_leaks_other_hostname(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json", "{}")
    dom = _write(tmp_path, "dom.json",
                 '{"domains":[{"domain":"some-other-service.zeabur.app"}]}')
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    # Query succeeded, expected domain absent -> valid negative, not a failure.
    assert ok is True
    assert ev["DOMAIN_HOSTNAME"] == "unexpected_or_absent"
    assert "some-other-service" not in "\n".join(f"{k}={v}" for k, v in ev.items())
    assert ev["DOMAIN_BINDING_PROVEN"] == "no"


def test_service_identity_and_env_binding(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json",
                 '{"id":"%s","name":"nexus-api-staging","environmentID":"%s"}'
                 % (EXPECTED_SERVICE_ID, EXPECTED_ENV_ID))
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True
    assert ev["SERVICE_ID_MATCH"] == "yes"
    assert ev["SERVICE_NAME"] == "nexus-api-staging"
    assert ev["ENVIRONMENT_ID_MATCH"] == "yes"
    assert ev["SERVICE_ID_PROVEN"] == "yes"
    assert ev["ENV_BINDING_PROVEN"] == "yes"


def test_deployment_safe_field_parsing_single_aug27(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json", "{}")
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json",
                 '[{"id":"dep_old","status":"RUNNING","createdAt":"2026-08-16T17:38:00Z"},'
                 '{"id":"dep_aug27","status":"BUILDING","createdAt":"2026-08-27T16:38:10Z"}]')
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True
    assert ev["DEPLOYMENT_COUNT"] == "2"
    assert ev["LATEST_DEPLOYMENT_ID"] == "dep_aug27"
    assert ev["AUG27_DEPLOYMENT_MATCH_COUNT"] == "1"
    assert ev["AUG27_DEPLOYMENT_AMBIGUOUS"] == "no"
    assert ev["AUG27_DEPLOYMENT_RECORD_FOUND"] == "yes"
    assert ev["AUG27_DEPLOYMENT_ID"] == "dep_aug27"
    assert "createdAt" in ev["DEPLOYMENT_SCHEMA_KEYS"]


def test_deployment_aug27_ambiguous_not_claimed(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json", "{}")
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json",
                 '[{"id":"dep_a","status":"RUNNING","createdAt":"2026-08-27T16:38:00Z"},'
                 '{"id":"dep_b","status":"RUNNING","createdAt":"2026-08-27T16:39:00Z"}]')
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True
    assert ev["AUG27_DEPLOYMENT_MATCH_COUNT"] == "2"
    assert ev["AUG27_DEPLOYMENT_AMBIGUOUS"] == "yes"
    assert ev["AUG27_DEPLOYMENT_RECORD_FOUND"] == "ambiguous"
    assert ev["AUG27_DEPLOYMENT_ID"] == "ambiguous"


# --------------------------------------------------------------------------
# Fail-closed contract
# --------------------------------------------------------------------------

def test_helper_fails_closed_on_bad_query_exit_code(tmp_path, monkeypatch) -> None:
    module = _load_helper()
    monkeypatch.setenv("SERVICE_QUERY_RC", "1")
    svc = _write(tmp_path, "svc.json", '{"id":"%s"}' % EXPECTED_SERVICE_ID)
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is False
    assert ev["SERVICE_QUERY_PASS"] == "no"
    assert ev["ALL_REQUIRED_QUERIES_PASS"] == "no"
    # main() must return non-zero (fail closed).
    assert module.main(["prog", str(svc), str(dom), str(dep)]) == 1


def test_helper_fails_closed_on_invalid_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DEPLOYMENT_QUERY_RC", raising=False)
    module = _load_helper()
    svc = _write(tmp_path, "svc.json", "{}")
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json", "ERROR: not logged in")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is False
    assert ev["DEPLOYMENT_QUERY_PASS"] == "no"
    assert ev["DEPLOYMENT_JSON_VALID"] == "no"
    assert ev["AUG27_DEPLOYMENT_RECORD_FOUND"] == "unknown"


def test_valid_negative_domain_absent_is_not_failure(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json", '{"id":"%s","name":"nexus-api-staging"}' % EXPECTED_SERVICE_ID)
    dom = _write(tmp_path, "dom.json", '{"domains":[]}')
    dep = _write(tmp_path, "dep.json", "[]")
    ev, ok = _evidence(module, svc, dom, dep)
    assert ok is True  # all queries succeeded; absent domain is legitimate
    assert ev["DOMAIN_QUERY_PASS"] == "yes"
    assert ev["DOMAIN_FOUND"] == "no"
    assert ev["DOMAIN_BINDING_PROVEN"] == "no"


def test_parser_never_emits_token_or_dsn_values(tmp_path) -> None:
    module = _load_helper()
    svc = _write(tmp_path, "svc.json",
                 '{"id":"%s","name":"nexus-api-staging",'
                 '"DATABASE_URL":"postgresql://u:p@h:5432/db",'
                 '"token":"zbtok_supersecretvalue"}' % EXPECTED_SERVICE_ID)
    dom = _write(tmp_path, "dom.json", "{}")
    dep = _write(tmp_path, "dep.json", "[]")
    lines, _ = module.analyze(str(svc), str(dom), str(dep))
    blob = "\n".join(lines)
    assert "postgresql://" not in blob
    assert "zbtok_supersecretvalue" not in blob
    assert "supersecret" not in blob
