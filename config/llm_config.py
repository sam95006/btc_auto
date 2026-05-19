import os


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def llm_enabled() -> bool:
    return _env_flag("NEXUS_LLM_ENABLE", "0")

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
SAMBANOVA_CHAT_COMPLETIONS_URL = "https://api.sambanova.ai/v1/chat/completions"

DEFAULT_TIMEOUT_SECONDS = int(os.getenv("NEXUS_LLM_TIMEOUT_SECONDS", "12"))
DEFAULT_MAX_COMPLETION_TOKENS = int(os.getenv("NEXUS_LLM_MAX_COMPLETION_TOKENS", "700"))

def task_refresh_seconds():
    return {
        "news": int(os.getenv("NEXUS_LLM_REFRESH_NEWS_SECONDS", "45")),
        "radar": int(os.getenv("NEXUS_LLM_REFRESH_RADAR_SECONDS", "25")),
        "roundtable": int(os.getenv("NEXUS_LLM_REFRESH_ROUNDTABLE_SECONDS", "60")),
        "reflection": int(os.getenv("NEXUS_LLM_REFRESH_REFLECTION_SECONDS", "90")),
        "agent": int(os.getenv("NEXUS_LLM_REFRESH_AGENT_SECONDS", "40")),
    }


def task_provider_defaults():
    return {
        "news": os.getenv("NEXUS_LLM_PROVIDER_NEWS", "groq_primary"),
        "radar": os.getenv("NEXUS_LLM_PROVIDER_RADAR", "groq_primary"),
        "roundtable": os.getenv("NEXUS_LLM_PROVIDER_ROUNDTABLE", "groq_secondary"),
        "reflection": os.getenv("NEXUS_LLM_PROVIDER_REFLECTION", "groq_secondary"),
        "agent": os.getenv("NEXUS_LLM_PROVIDER_AGENT", "sambanova"),
    }


def task_model_defaults():
    return {
        "news": os.getenv("NEXUS_LLM_MODEL_NEWS", "llama-3.3-70b-specdec"),
        "radar": os.getenv("NEXUS_LLM_MODEL_RADAR", "llama-3.3-70b-specdec"),
        "roundtable": os.getenv("NEXUS_LLM_MODEL_ROUNDTABLE", "mixtral-8x7b-32768"),
        "reflection": os.getenv("NEXUS_LLM_MODEL_REFLECTION", "mixtral-8x7b-32768"),
        "agent": os.getenv("NEXUS_LLM_MODEL_AGENT", "Meta-Llama-3.1-405B-Instruct"),
        "agent_fallback": os.getenv("NEXUS_LLM_MODEL_AGENT_FALLBACK", "Meta-Llama-3.1-70B-Instruct"),
    }

MODEL_FALLBACKS = {
    "llama-3.3-70b-specdec": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
    "mixtral-8x7b-32768": ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
    "Meta-Llama-3.1-405B-Instruct": ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1"],
    "Meta-Llama-3.1-70B-Instruct": ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1"],
}

PROVIDER_KEY_ENV = {
    "groq_primary": "GROQ_API_KEY_PRIMARY",
    "groq_secondary": "GROQ_API_KEY_SECONDARY",
    "sambanova": "SAMBANOVA_API_KEY",
}

PROVIDER_ENDPOINTS = {
    "groq_primary": GROQ_CHAT_COMPLETIONS_URL,
    "groq_secondary": GROQ_CHAT_COMPLETIONS_URL,
    "sambanova": SAMBANOVA_CHAT_COMPLETIONS_URL,
}

PROVIDER_LABELS = {
    "groq_primary": "groq",
    "groq_secondary": "groq",
    "sambanova": "sambanova",
}

ALLOWED_TASKS = {"news", "radar", "roundtable", "reflection", "agent"}
