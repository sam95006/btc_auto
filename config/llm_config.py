import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def llm_enabled() -> bool:
    default = "1" if BOLD_TESTNET_ENABLED else "0"
    return _env_flag("NEXUS_LLM_ENABLE", default)

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
        "chat": int(os.getenv("NEXUS_LLM_REFRESH_CHAT_SECONDS", "0")),
        "radar_proposal": int(os.getenv("NEXUS_LLM_REFRESH_RADAR_PROPOSAL_SECONDS", "35")),
        "trade_proposer": int(os.getenv("NEXUS_LLM_REFRESH_TRADE_PROPOSER_SECONDS", "20")),
        "regime_classifier": int(os.getenv("NEXUS_LLM_REFRESH_REGIME_SECONDS", "1800")),
        "post_mortem": int(os.getenv("NEXUS_LLM_REFRESH_POST_MORTEM_SECONDS", "0")),
    }


def task_provider_defaults():
    return {
        "news": os.getenv("NEXUS_LLM_PROVIDER_NEWS", "groq_primary"),
        "radar": os.getenv("NEXUS_LLM_PROVIDER_RADAR", "groq_primary"),
        "roundtable": os.getenv("NEXUS_LLM_PROVIDER_ROUNDTABLE", "groq_secondary"),
        "reflection": os.getenv("NEXUS_LLM_PROVIDER_REFLECTION", "groq_secondary"),
        "agent": os.getenv("NEXUS_LLM_PROVIDER_AGENT", "sambanova"),
        "chat": os.getenv("NEXUS_LLM_PROVIDER_CHAT", "groq_primary"),
        "trade_proposer": os.getenv("NEXUS_LLM_PROVIDER_TRADE_PROPOSER", "groq_primary"),
        "regime_classifier": os.getenv("NEXUS_LLM_PROVIDER_REGIME", "groq_secondary"),
        "post_mortem": os.getenv("NEXUS_LLM_PROVIDER_POST_MORTEM", "groq_secondary"),
    }


def task_model_defaults():
    return {
        "news": os.getenv("NEXUS_LLM_MODEL_NEWS", "llama-3.3-70b-specdec"),
        "radar": os.getenv("NEXUS_LLM_MODEL_RADAR", "llama-3.3-70b-specdec"),
        "roundtable": os.getenv("NEXUS_LLM_MODEL_ROUNDTABLE", "mixtral-8x7b-32768"),
        "reflection": os.getenv("NEXUS_LLM_MODEL_REFLECTION", "mixtral-8x7b-32768"),
        "agent": os.getenv("NEXUS_LLM_MODEL_AGENT", "Meta-Llama-3.1-405B-Instruct"),
        "agent_fallback": os.getenv("NEXUS_LLM_MODEL_AGENT_FALLBACK", "Meta-Llama-3.1-70B-Instruct"),
        "chat": os.getenv("NEXUS_LLM_MODEL_CHAT", "llama-3.3-70b-versatile"),
        "radar_proposal": os.getenv("NEXUS_LLM_MODEL_RADAR_PROPOSAL", os.getenv("NEXUS_LLM_MODEL_TRADE_PROPOSAL", "llama-3.3-70b-versatile")),
        "trade_proposer": os.getenv("NEXUS_LLM_MODEL_TRADE_PROPOSER", "llama-3.3-70b-versatile"),
        "regime_classifier": os.getenv("NEXUS_LLM_MODEL_REGIME", "mixtral-8x7b-32768"),
        "post_mortem": os.getenv("NEXUS_LLM_MODEL_POST_MORTEM", "mixtral-8x7b-32768"),
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

ALLOWED_TASKS = {
    "news",
    "radar",
    "radar_proposal",
    "roundtable",
    "reflection",
    "agent",
    "chat",
    "trade_proposer",
    "regime_classifier",
    "post_mortem",
}
