#!/usr/bin/env python3
"""Scaffold a new Suzent AgentSkill in the user bucket.

Creates ~/.suzent/skills/user/<name>/ with a starter SKILL.md and empty
scripts/, references/, and assets/ directories.

Usage:
    python scaffold.py <name> --description "..." [--force]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SKILL_TEMPLATE = """\
---
name: {name}
description: {description}
---

## Overview

<One paragraph: what this skill does and the situations it is for.>

## Workflow

<Step-by-step instructions for the agent. Explain *why* where it helps the
agent generalize, rather than only listing rigid rules.>

## Examples

<2-3 concrete usage examples.>
"""

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def user_skills_dir() -> Path:
    """Resolve the user skills bucket, honoring SKILLS_DIR / app-data overrides."""
    # Explicit override used by the bundled app.
    env_dir = os.getenv("SUZENT_USER_SKILLS_DIR")
    if env_dir:
        return Path(env_dir)
    app_data = os.getenv("SUZENT_APP_DATA")
    base = Path(app_data) if app_data else (Path.home() / ".suzent")
    return base / "skills" / "user"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new Suzent skill.")
    parser.add_argument("name", help="Skill name (lowercase, kebab-case)")
    parser.add_argument(
        "--description",
        "-d",
        required=True,
        help="One-line trigger description (what/when the skill fires)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing skill directory",
    )
    args = parser.parse_args()

    name = args.name.strip()
    if not NAME_RE.match(name):
        print(
            f"error: invalid skill name '{name}' "
            "(use lowercase letters, digits, and hyphens)",
            file=sys.stderr,
        )
        return 2

    target = user_skills_dir() / name
    skill_md = target / "SKILL.md"

    if skill_md.exists() and not args.force:
        print(
            f"error: skill already exists at {target} (use --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    for sub in ("scripts", "references", "assets"):
        (target / sub).mkdir(parents=True, exist_ok=True)

    # Description is single-line; collapse any stray newlines for the flat parser.
    description = " ".join(args.description.split())
    skill_md.write_text(
        SKILL_TEMPLATE.format(name=name, description=description),
        encoding="utf-8",
    )

    print(f"Scaffolded skill at: {target}")
    print(f"  - {skill_md}")
    print("Next:")
    print(f"  1. Edit {skill_md}")
    print("  2. suzent skill reload")
    print(f"  3. suzent skill toggle {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
