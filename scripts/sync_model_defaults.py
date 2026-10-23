"""Refresh conservative provider defaults from LiteLLM's public model catalog."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx


CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
DEFAULTS_PATH = Path(__file__).resolve().parents[1] / "config/provider_defaults.json"

# Each family yields its newest matching model. Counts above one are used only
# where a provider has a single general-purpose family with useful tiers.
FAMILIES: dict[str, tuple[tuple[str, int], ...]] = {
    "openai": (
        (r"gpt-(?P<version>\d+(?:\.\d+)?)-sol", 1),
        (r"gpt-(?P<version>\d+(?:\.\d+)?)-luna", 1),
        (r"gpt-(?P<version>\d+(?:\.\d+)?)-astra", 1),
    ),
    "anthropic": tuple(
        (rf"claude-{tier}-(?P<version>\d+-\d+)", 1)
        for tier in ("opus", "sonnet", "haiku")
    ),
    "gemini": tuple(
        (rf"gemini-(?P<version>\d+\.\d+)-{tier}(?:-preview)?", 1)
        for tier in ("pro", "flash", "flash-lite")
    ),
    # Grok 4.20 predates 4.7, so decimal-like versions cannot be sorted as
    # semantic versions; select the numbered flagship line conservatively.
    "xai": ((r"grok-(?P<version>\d+(?:\.[1-9])?)", 2),),
    "dashscope": tuple(
        (rf"qwen(?P<version>\d+\.\d+)-{tier}", 1) for tier in ("max", "flash")
    ),
    "deepseek": tuple(
        (rf"deepseek-v(?P<version>\d+(?:\.\d+)?)-{tier}", 1)
        for tier in ("pro", "flash")
    ),
    "minimax": ((r"MiniMax-M(?P<version>\d+(?:\.\d+)?)", 2),),
    "moonshot": ((r"kimi-k(?P<version>\d+(?:\.\d+)?)(?:-code)?", 3),),
    "zai": tuple(
        (rf"glm-(?P<version>\d+(?:\.\d+)?){suffix}", 1) for suffix in ("", "-flash")
    ),
    "xiaomi_mimo": tuple(
        (rf"mimo-v(?P<version>\d+\.\d+)-{tier}", 1) for tier in ("pro", "flash")
    ),
}


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.split(r"[.-]", value))


def _display_name(model: str) -> str:
    name = model.replace("-", " ").title()
    name = re.sub(r"(?<=\d) (?=\d)", ".", name)
    for original, replacement in (
        ("Gpt", "GPT"),
        ("Glm", "GLM"),
        ("Mimo", "MiMo"),
        ("Minimax", "MiniMax"),
        ("Deepseek", "DeepSeek"),
    ):
        name = name.replace(original, replacement)
    return name


def select_default_models(
    catalog: dict[str, object],
) -> dict[str, list[dict[str, str]]]:
    """Choose recent general-purpose chat models from named provider families."""
    candidates: dict[str, set[str]] = {provider: set() for provider in FAMILIES}
    for key, info in catalog.items():
        if not isinstance(info, dict) or info.get("mode") != "chat":
            continue
        if "/" in key:
            provider, model = key.split("/", 1)
        else:
            provider, model = info.get("litellm_provider"), key
        if provider in candidates and "/" not in model:
            candidates[provider].add(model)

    selected: dict[str, list[dict[str, str]]] = {}
    for provider, families in FAMILIES.items():
        model_ids: list[str] = []
        for pattern, count in families:
            matches: list[tuple[tuple[int, ...], bool, str]] = []
            for model in candidates[provider]:
                match = re.fullmatch(pattern, model)
                if match:
                    matches.append(
                        (
                            _version(match.group("version")),
                            "preview" not in model,
                            model,
                        )
                    )
            matches.sort(reverse=True)
            model_ids.extend(model for _, _, model in matches[:count])
        if model_ids:
            selected[provider if provider != "zai" else "zhipuai"] = [
                {
                    "id": f"{provider}/{model}",
                    "name": _display_name(model),
                }
                for model in dict.fromkeys(model_ids)
            ]
    return selected


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(CATALOG_URL)
        response.raise_for_status()
        catalog = response.json()
    selected = select_default_models(catalog)
    existing = (
        json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
        if DEFAULTS_PATH.exists()
        else {}
    )
    existing.update(selected)
    DEFAULTS_PATH.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for provider, models in sorted(selected.items()):
        print(f"{provider}: {', '.join(model['id'] for model in models)}")


if __name__ == "__main__":
    asyncio.run(main())
