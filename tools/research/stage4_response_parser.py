"""Stage 4 LLM response content extraction and JSON parsing."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

SECRET_PATTERNS = re.compile(
    r"(api[_-]?key\s*[=:]\s*\S+|authorization|bearer\s+[a-z0-9._-]+|sk-[a-z0-9._-]{8,})",
    re.IGNORECASE,
)


def safe_excerpt(text: str, limit: int = 300) -> str:
    snippet = (text or "")[:limit]
    return SECRET_PATTERNS.sub("[REDACTED]", snippet)


def extract_openai_compat_content(raw: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """Return (content_text, response_path_used, finish_reason)."""
    choices = raw.get("choices") or []
    if not choices:
        return "", "choices[missing]", None
    choice = choices[0] or {}
    finish = choice.get("finish_reason")
    message = choice.get("message") or {}

    content = message.get("content")
    if content is not None:
        text = _normalize_content_piece(content)
        if text:
            return text, "choices[0].message.content", finish

    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        fn = (tool_calls[0] or {}).get("function") or {}
        args = fn.get("arguments") or ""
        if args:
            return str(args), "choices[0].message.tool_calls[0].function.arguments", finish

    delta = choice.get("delta") or {}
    delta_content = delta.get("content")
    if delta_content is not None:
        text = _normalize_content_piece(delta_content)
        if text:
            return text, "choices[0].delta.content", finish

    text_field = choice.get("text")
    if text_field:
        return str(text_field), "choices[0].text", finish

    return "", "choices[0].message.content", finish


def extract_anthropic_content(raw: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    blocks = raw.get("content") or []
    for block in blocks:
        if (block or {}).get("type") == "text":
            text = str(block.get("text") or "")
            if text:
                return text, "content[].text", raw.get("stop_reason")
    return "", "content[].text", raw.get("stop_reason")


def extract_gemini_content(raw: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    parts = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    if parts:
        text = str(parts[0].get("text") or "")
        if text:
            return text, "candidates[0].content.parts[0].text", None
    return "", "candidates[0].content.parts[0].text", None


def extract_ollama_content(raw: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    content = (raw.get("message") or {}).get("content")
    if content is not None:
        text = _normalize_content_piece(content)
        if text:
            return text, "message.content", raw.get("done_reason")
    return "", "message.content", raw.get("done_reason")


def _normalize_content_piece(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "").strip()
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def _repair_truncated_json(raw: str) -> str:
    """Best-effort close for truncated JSON object payloads."""
    text = (raw or "").strip()
    if not text.startswith("{"):
        return ""
    trimmed = re.sub(r',\s*"[^"]*$', "", text)
    trimmed = re.sub(r',\s*$', "", trimmed)
    while trimmed.count("{") > trimmed.count("}"):
        trimmed += "}"
    return trimmed


def parse_llm_response_text(text: str) -> Tuple[Dict[str, Any], bool, str]:
    """Parse model text into dict. Returns (parsed, ok, parse_error_type)."""
    raw = (text or "").strip()
    if not raw:
        return {}, False, "content_empty"

    candidates = [raw]
    if raw.startswith("```"):
        fenced = re.sub(r"^```(?:json)?\s*", "", raw)
        fenced = re.sub(r"\s*```$", "", fenced).strip()
        candidates.insert(0, fenced)

    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match and brace_match.group(0) not in candidates:
        candidates.append(brace_match.group(0))

    repaired = _repair_truncated_json(raw)
    if repaired and repaired not in candidates:
        candidates.append(repaired)

    last_err = "json_decode_error"
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, True, ""
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0], True, ""
            last_err = "json_not_object"
        except json.JSONDecodeError:
            continue

    return {}, False, last_err
