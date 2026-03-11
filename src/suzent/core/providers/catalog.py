"""
Provider catalog: UI configuration and environment variable mapping.

PROVIDER_CONFIG drives the settings UI — each entry defines credential fields
and a curated list of default models. Users can also fetch live models or add
custom model IDs on top of these defaults.

PROVIDER_ENV_KEYS maps provider IDs to the environment variables that hold
their API keys, used by resolve_api_key() and GenericLiteLLMProvider.
For providers not listed, resolve_api_key falls back to <PROVIDER_ID>.upper()_API_KEY.
"""

from typing import Dict, List

PROVIDER_CONFIG: List[dict] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "default_models": [
            {"id": "openai/gpt-4.1", "name": "GPT-4.1"},
            {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini"},
            {"id": "openai/o3", "name": "o3"},
            {"id": "openai/o4-mini", "name": "o4-mini"},
        ],
        "fields": [
            {
                "key": "OPENAI_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
            {
                "key": "OPENAI_BASE_URL",
                "label": "Base URL (Optional)",
                "placeholder": "https://api.openai.com/v1",
                "type": "text",
            },
        ],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "default_models": [
            {"id": "anthropic/claude-opus-4-6", "name": "Claude Opus 4.6"},
            {"id": "anthropic/claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
            {"id": "anthropic/claude-haiku-4-5", "name": "Claude Haiku 4.5"},
        ],
        "fields": [
            {
                "key": "ANTHROPIC_API_KEY",
                "label": "API Key",
                "placeholder": "sk-ant-...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "default_models": [
            {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
            {"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            {"id": "gemini/gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
        ],
        "fields": [
            {
                "key": "GEMINI_API_KEY",
                "label": "API Key",
                "placeholder": "AIza...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "xai",
        "label": "xAI (Grok)",
        "default_models": [
            {"id": "xai/grok-3", "name": "Grok 3"},
            {"id": "xai/grok-3-mini", "name": "Grok 3 Mini"},
            {"id": "xai/grok-3-fast", "name": "Grok 3 Fast"},
        ],
        "fields": [
            {
                "key": "XAI_API_KEY",
                "label": "API Key",
                "placeholder": "xai-...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "default_models": [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 (Chat)"},
            {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek R1 (Reasoner)"},
        ],
        "fields": [
            {
                "key": "DEEPSEEK_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "default_models": [
            {"id": "minimax/MiniMax-M2.5", "name": "MiniMax M2.5"},
            {"id": "minimax/MiniMax-M2.1", "name": "MiniMax M2.1"},
        ],
        "fields": [
            {
                "key": "MINIMAX_API_KEY",
                "label": "API Key",
                "placeholder": "...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "moonshot",
        "label": "Moonshot (Kimi)",
        "default_models": [
            {"id": "moonshot/moonshot-v1-128k", "name": "Kimi v1 128K"},
            {"id": "moonshot/moonshot-v1-32k", "name": "Kimi v1 32K"},
            {"id": "moonshot/moonshot-v1-8k", "name": "Kimi v1 8K"},
        ],
        "fields": [
            {
                "key": "MOONSHOT_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "zhipuai",
        "label": "Zhipu AI (GLM)",
        "default_models": [
            {"id": "zai/glm-4.7-flash", "name": "GLM-4.7 Flash"},
        ],
        "fields": [
            {
                "key": "ZAI_API_KEY",
                "label": "API Key",
                "placeholder": "...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "default_models": [],  # Dynamic — aggregates 300+ models
        "fields": [
            {
                "key": "OPENROUTER_API_KEY",
                "label": "API Key",
                "placeholder": "sk-or-...",
                "type": "secret",
            },
        ],
    },
    {
        "id": "litellm_proxy",
        "label": "LiteLLM Proxy",
        "default_models": [],  # Dynamic
        "fields": [
            {
                "key": "LITELLM_MASTER_KEY",
                "label": "Master Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
            {
                "key": "LITELLM_BASE_URL",
                "label": "Base URL",
                "placeholder": "http://localhost:4000",
                "type": "text",
            },
        ],
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "default_models": [],  # Dynamic — depends on locally pulled models
        "fields": [
            {
                "key": "OLLAMA_BASE_URL",
                "label": "Base URL",
                "placeholder": "http://localhost:11434",
                "type": "text",
            },
            {
                "key": "OLLAMA_API_KEY",
                "label": "API Key (Optional)",
                "placeholder": "...",
                "type": "secret",
            },
        ],
    },
]

# Maps provider ID → env var names to check (in priority order).
# For providers not listed, resolve_api_key falls back to <PROVIDER_ID>.upper()_API_KEY.
PROVIDER_ENV_KEYS: Dict[str, List[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
    "moonshot": ["MOONSHOT_API_KEY"],
    "zhipuai": ["ZHIPUAI_API_KEY"],
    "zai": ["ZHIPUAI_API_KEY"],  # Z.ai is Zhipu's new branding; shares the same key
    "ollama": ["OLLAMA_BASE_URL"],  # key-less; base URL doubles as identifier
    "bedrock": [],  # uses AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
}

# Providers that speak the OpenAI chat completions API at a custom base URL.
# Used by both OpenAICompatProvider (for model discovery) and model_factory (for inference).
# LiteLLM's get_valid_models() does not support these, so we query /v1/models directly.
# Index of PROVIDER_CONFIG by provider ID for O(1) lookup.
PROVIDER_CONFIG_BY_ID: Dict[str, dict] = {
    entry["id"]: entry for entry in PROVIDER_CONFIG
}

OPENAI_COMPAT_PROVIDERS: Dict[str, str] = {
    "minimax": "https://api.minimaxi.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "zhipuai": "https://open.bigmodel.cn/api/paas/v4",
    "zai": "https://api.z.ai/api/paas/v4",  # Z.ai (Zhipu's new domain)
    "perplexity": "https://api.perplexity.ai",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "sambanova": "https://api.sambanova.ai/v1",
}
