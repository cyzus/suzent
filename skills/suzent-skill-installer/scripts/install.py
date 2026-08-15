#!/usr/bin/env python3
"""Install a Suzent AgentSkill from a Git repo, ZIP URL, or owner/repo shorthand.

Fetch-and-copy only — never executes code from the source at install time.
The agent invokes this on the user's explicit request, so there is no separate
trust prompt: it fetches the source the user named, validates it is a real
skill, and copies it in.

Usage:
    python install.py <source> [--name NAME] [--activate]
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MAX_EXTRACTED_BYTES = 50 * 1024 * 1024  # 50 MB cap
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHORTHAND_RE = re.compile(r"^[\w.-]+/[\w.-]+(/.+)?$")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# --- source resolution -----------------------------------------------------


def resolve_source(source: str) -> tuple[str, str]:
    """Return (kind, fetch_url) for a source string.

    kind is one of: "git", "zip", "shorthand".
    """
    s = source.strip()
    if s.endswith(".git") or s.startswith("git@"):
        return "git", s
    if s.endswith(".zip"):
        return "zip", s
    if s.startswith(("http://", "https://")):
        # Generic URL: treat .git-less GitHub URLs as git, else zip-by-extension.
        return "git", s
    if SHORTHAND_RE.match(s):
        owner_repo = "/".join(s.split("/")[:2])
        return "shorthand", f"https://github.com/{owner_repo}.git"
    raise ValueError(f"Unrecognized source: {source!r}")


def subpath_of(source: str) -> str:
    """For owner/repo/path shorthand, return the trailing path within the repo."""
    if SHORTHAND_RE.match(source) and source.count("/") >= 2:
        return "/".join(source.split("/")[2:])
    return ""


def infer_name(source: str, explicit: str | None) -> str:
    if explicit:
        name = explicit
    else:
        cleaned = source.rstrip("/").removesuffix(".git").removesuffix(".zip")
        name = cleaned.split("/")[-1]
    name = name.strip().lower()
    if not NAME_RE.match(name):
        raise ValueError(f"Invalid inferred skill name: {name!r} (use --name)")
    return name


# --- fetch -----------------------------------------------------------------


def fetch_git(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.rmtree(dest / ".git", ignore_errors=True)


def fetch_zip(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (validated upstream)
        data = resp.read(MAX_EXTRACTED_BYTES + 1)
    if len(data) > MAX_EXTRACTED_BYTES:
        raise ValueError("Download exceeds size cap")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        total = sum(i.file_size for i in zf.infolist())
        if total > MAX_EXTRACTED_BYTES:
            raise ValueError("Archive expands beyond size cap")
        zf.extractall(dest)


# --- validation ------------------------------------------------------------


def find_skill_dir(root: Path, subpath: str) -> Path:
    """Locate the directory containing SKILL.md."""
    if subpath:
        candidate = root / subpath
        if (candidate / "SKILL.md").exists():
            return candidate
    if (root / "SKILL.md").exists():
        return root
    # Single-child unwrap (ZIP/tarball often nest under one folder).
    children = [c for c in root.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / "SKILL.md").exists():
        return children[0]
    matches = sorted(root.rglob("SKILL.md"))
    if matches:
        return matches[0].parent
    raise ValueError("No SKILL.md found in the fetched source")


def validate_frontmatter(skill_md: Path) -> None:
    """Mirror Suzent's loader: require flat name: and description: fields."""
    content = skill_md.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        raise ValueError("SKILL.md is missing YAML frontmatter")
    meta: dict[str, str] = {}
    for line in m.group(1).strip().splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("\"'")
    missing = [k for k in ("name", "description") if not meta.get(k)]
    if missing:
        raise ValueError(
            f"SKILL.md frontmatter missing required field(s): {', '.join(missing)}"
        )


# --- install ---------------------------------------------------------------


def user_skills_dir() -> Path:
    env_dir = os.getenv("SUZENT_USER_SKILLS_DIR")
    if env_dir:
        return Path(env_dir)
    app_data = os.getenv("SUZENT_APP_DATA")
    base = Path(app_data) if app_data else (Path.home() / ".suzent")
    return base / "skills" / "user"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a Suzent skill.")
    parser.add_argument("source", help="Git URL, ZIP URL, or owner/repo[/path]")
    parser.add_argument("--name", help="Override the installed skill name")
    parser.add_argument(
        "--activate", action="store_true", help="(informational) enable after install"
    )
    args = parser.parse_args()

    try:
        kind, fetch_url = resolve_source(args.source)
        name = infer_name(args.source, args.name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    target = user_skills_dir() / name
    if (target / "SKILL.md").exists():
        print(f"error: skill '{name}' already installed at {target}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="suzent-skill-") as tmp:
        tmp_root = Path(tmp) / "src"
        tmp_root.mkdir()
        try:
            if kind in ("git", "shorthand"):
                fetch_git(fetch_url, tmp_root)
            else:
                fetch_zip(fetch_url, tmp_root)

            skill_dir = find_skill_dir(tmp_root, subpath_of(args.source))
            validate_frontmatter(skill_dir / "SKILL.md")

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill_dir, target)
        except subprocess.CalledProcessError as e:
            print(f"error: fetch failed: {e.stderr or e}", file=sys.stderr)
            shutil.rmtree(target, ignore_errors=True)
            return 1
        except Exception as e:  # noqa: BLE001 - report and clean up
            print(f"error: {e}", file=sys.stderr)
            shutil.rmtree(target, ignore_errors=True)
            return 1

    print(f"Installed skill '{name}' to {target}")
    print("Next:")
    print("  1. suzent skill reload")
    if args.activate:
        print(f"  2. suzent skill toggle {name}   # enable it")
    else:
        print(f"  2. suzent skill toggle {name}   # enable when ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
