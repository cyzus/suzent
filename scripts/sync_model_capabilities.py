"""Sync model capability metadata for automation.

This wrapper exists so GitHub Actions can refresh tracked capability files
without embedding Python one-liners in workflow YAML.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Awaitable, Callable


SyncFunction = Callable[[], Awaitable[dict[str, int]]]


async def run_sync(sync_func: SyncFunction | None = None) -> dict[str, int]:
    """Run the LiteLLM capability sync and return provider update counts."""
    if sync_func is None:
        from suzent.core.model_registry import sync_from_litellm

        sync_func = sync_from_litellm

    return await sync_func()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh model capabilities from LiteLLM metadata."
    )
    parser.add_argument(
        "--to-repo",
        action="store_true",
        help=(
            "Write updates into tracked config/capabilities files instead of "
            "the local overlay."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON stats instead of a human-readable summary.",
    )
    return parser


def main(argv: list[str] | None = None, sync_func: SyncFunction | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.to_repo:
        os.environ["SUZENT_CAPABILITIES_TO_REPO"] = "1"

    stats = asyncio.run(run_sync(sync_func=sync_func))

    if args.json:
        print(json.dumps(stats, sort_keys=True))
    else:
        total = sum(stats.values())
        providers = len(stats)
        print(f"Updated {total} model capability entries across {providers} providers.")
        for provider_id, count in sorted(stats.items()):
            print(f"- {provider_id}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
