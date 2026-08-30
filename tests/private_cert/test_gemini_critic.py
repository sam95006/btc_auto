from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from backend.nexus_private_cert import gemini_provider as gp
from backend.nexus_private_cert.certifier import AI_PROFILES, GEMINI_PROFILE


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_payload(text='{"ok": true, "ping": "pong"}'):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _patch_urlopen(monkeypatch, fn):
    monkeypatch.setattr(gp, "urlopen", fn)


def _http_error(code):
    def _raise(req, timeout=None):
        raise HTTPError("u", code, "err", {}, io.BytesIO(b'{"error":"x"}'))
    return _raise


# --------------------------------------------------------------------------

def test_gemini_not_configured(monkeypatch):
    monkeypatch.delenv(gp.GEMINI_ENV_KEY, raising=False)
    r = gp.gemini_smoke()
    assert r["result_status"] == "NOT_CONFIGURED" and r["can_approve_order"] is False


def test_gemini_cannot_approve_order():
    assert gp.GeminiCriticProvider().can_approve_order is False


def test_gemini_structured_success(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    _patch_urlopen(monkeypatch, lambda req, timeout=None: _Resp(_ok_payload()))
    r = gp.gemini_smoke()
    assert r["result_status"] == "REAL_API_PASS"


def test_gemini_model_unavailable(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    _patch_urlopen(monkeypatch, _http_error(404))
    assert gp.gemini_smoke()["result_status"] == "MODEL_UNAVAILABLE"


def test_gemini_auth_failed(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    _patch_urlopen(monkeypatch, _http_error(401))
    assert gp.gemini_smoke()["result_status"] == "AUTH_FAILED"


def test_gemini_rate_limited(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    _patch_urlopen(monkeypatch, _http_error(429))
    assert gp.gemini_smoke()["result_status"] == "RATE_LIMITED"


def test_gemini_timeout(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")

    def _to(req, timeout=None):
        raise TimeoutError()
    _patch_urlopen(monkeypatch, _to)
    assert gp.gemini_smoke()["result_status"] == "TIMEOUT"


def test_gemini_malformed_response(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    _patch_urlopen(monkeypatch, lambda req, timeout=None: _Resp({"candidates": []}))
    assert gp.gemini_smoke()["result_status"] == "BAD_RESPONSE_SCHEMA"


def test_gemini_redaction_applied(monkeypatch):
    # A secret-like token in the prompt must be redacted before it is sent.
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "k")
    captured = {}

    def _cap(req, timeout=None):
        captured["body"] = req.data.decode("utf-8")
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _Resp(_ok_payload())

    _patch_urlopen(monkeypatch, _cap)
    schema = {"title": "nexus_smoke_v1", "required": ["ok", "ping"],
              "properties": {"ok": {"type": "boolean"}, "ping": {"type": "string"}}}
    gp.GeminiCriticProvider().complete_json(
        prompt="reflection api_key=TOPSECRETVALUE password=HUSH123 note", schema=schema, model_id="gemini-3.7-flash")
    body = captured["body"]
    # The external-provider redaction boundary masks secret-bearing values.
    assert "TOPSECRETVALUE" not in body and "HUSH123" not in body
    assert "REDACTED" in body
    # Key must be in the x-goog-api-key header, never in the URL/query/body.
    assert "x-goog-api-key" in captured["headers"]
    assert "key=" not in captured["body"]


def test_gemini_key_never_in_url(monkeypatch):
    monkeypatch.setenv(gp.GEMINI_ENV_KEY, "SECRETKEY")
    seen = {}

    def _cap(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(_ok_payload())
    _patch_urlopen(monkeypatch, _cap)
    gp.gemini_smoke()
    assert "SECRETKEY" not in seen["url"] and "key=" not in seen["url"]


# --------------------------------------------------------------------------
# Required active set: Gemini is the critic; SambaNova is not required.
# --------------------------------------------------------------------------

def test_required_set_has_gemini_not_sambanova():
    assert GEMINI_PROFILE == "GEMINI_INDEPENDENT_CRITIC"
    assert "GEMINI_INDEPENDENT_CRITIC" in AI_PROFILES
    assert "SAMBANOVA_INDEPENDENT_CRITIC" not in AI_PROFILES
    assert set(AI_PROFILES) == {
        "GROQ_MAIN_REASONER", "GROQ_REFLECTION_REASONER",
        "CEREBRAS_RESEARCH_NORMALIZER", "GEMINI_INDEPENDENT_CRITIC",
    }
