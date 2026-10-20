"""Conservative, offline role matching for explicitly enabled models."""

from suzent.core.model_registry import ModelRegistry


def recommend_roles(
    registry: ModelRegistry,
    enabled_models: list[str],
    configured_providers: set[str],
    primary: str,
) -> dict[str, list[str]]:
    """Never infer specialist capabilities from names or provider membership."""
    eligible = sorted(
        {m for m in enabled_models if m.partition("/")[0] in configured_providers}
    )
    if primary not in eligible:
        raise ValueError("Primary model must be enabled on a configured provider")
    caps = {m: registry.get_capabilities(m) for m in eligible}
    primary_cap = caps[primary]
    if primary_cap and primary_cap.mode != "chat":
        raise ValueError("Primary model must support chat")

    def rank(model: str) -> tuple[bool, float, str]:
        cap = caps[model]
        cost = cap.input_cost_per_token + cap.output_cost_per_token if cap else 0
        # Zero commonly means missing pricing, not a free model.
        return cost <= 0, cost if cost > 0 else float("inf"), model

    known = {m: c for m, c in caps.items() if c is not None and not c.is_stub}
    chat = [m for m, c in known.items() if c.mode == "chat"]
    priced = [m for m in chat if not rank(m)[0]]
    cheap = min(priced, key=rank) if priced else primary
    roles = {"primary": [primary], "cheap": [cheap]}
    for role in (
        "title",
        "suggestion",
        "memory_extraction",
        "decision",
        "goal_judge",
        "permission_review",
    ):
        roles[role] = [cheap]
    roles["dream"] = [primary]
    candidates = {
        "vision": [
            m for m, c in known.items() if c.mode == "chat" and c.supports_vision
        ],
        "embedding": [m for m, c in known.items() if c.mode == "embedding"],
        "image_generation": [
            m for m, c in known.items() if c.mode == "image_generation"
        ],
        "image_edit": [m for m, c in known.items() if c.supports_image_edit is True],
        "video_generation": [
            m for m, c in known.items() if c.mode == "video_generation"
        ],
        "tts": [m for m, c in known.items() if c.mode == "tts"],
    }
    for role, models in candidates.items():
        selected = (
            primary
            if role == "vision" and primary in models
            else min(models, key=rank, default=None)
        )
        roles[role] = [selected] if selected else []
    return roles
