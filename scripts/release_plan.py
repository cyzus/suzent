#!/usr/bin/env python3
"""Validate release declarations and prepare independent product release plans."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any

if __package__:
    from . import bump_version as desktop
    from .generate_mobile_version import version_outputs
else:
    import bump_version as desktop
    from generate_mobile_version import version_outputs

PRODUCTS = ("desktop", "mobile", "browser")
TAG_PREFIXES = {"desktop": "v", "mobile": "mobile-v", "browser": "browser-v"}
BROWSER_SOURCE = "extensions/browser/manifest.json"
RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
CHANGES = ".releases/changes/"
MOBILE_SOURCE = "packages/mobile-contract/version.json"
MOBILE_FILES = (
    MOBILE_SOURCE,
    "apps/ios/Config/Version.xcconfig",
    "apps/android/version.properties",
)
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def git(root: Path, *args: str, strip: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    return result.strip() if strip else result


def read(root: Path, path: str, source: str | None = None) -> str:
    if source is None:
        return (root / path).read_text(encoding="utf-8")
    return git(root, "show", f"{source}:{path}", strip=False)


def exists(root: Path, path: str, source: str | None = None) -> bool:
    if source is None:
        return (root / path).exists()
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{source}:{path}"],
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def load(root: Path, path: str, source: str | None = None) -> Any:
    return json.loads(read(root, path, source))


def write(root: Path, path: str, data: Any) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"Invalid version: {value!r}")
    return tuple(map(int, value.split(".")))


def declarations(root: Path, source: str | None = None) -> dict[str, dict[str, Any]]:
    paths = (
        git(root, "ls-tree", "-r", "--name-only", source, "--", CHANGES).splitlines()
        if source
        else [
            p.relative_to(root).as_posix()
            for p in (root / CHANGES).rglob("*")
            if p.is_file()
        ]
    )
    result = {}
    for path in sorted(paths):
        if not re.fullmatch(r"\.releases/changes/[a-z0-9][a-z0-9-]*\.json", path):
            raise ValueError(f"Invalid declaration filename: {path}")
        item = load(root, path, source)
        if not isinstance(item, dict) or set(item) - {"products", "summary", "reason"}:
            raise ValueError(f"Invalid declaration fields: {path}")
        products = item.get("products")
        if (
            not isinstance(products, dict)
            or not products
            or set(products) - set(PRODUCTS)
        ):
            raise ValueError(f"Invalid products: {path}")
        if any(not isinstance(v, str) or v not in RANK for v in products.values()):
            raise ValueError(f"Invalid release impact: {path}")
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            raise ValueError(f"A summary is required: {path}")
        if "none" in products.values() and (
            not isinstance(item.get("reason"), str) or not item["reason"].strip()
        ):
            raise ValueError(f"A reason is required for none: {path}")
        result[path] = item
    return result


def product_version(root: Path, product: str, source: str | None = None) -> str:
    path = {
        "desktop": "src-tauri/tauri.conf.json",
        "mobile": MOBILE_SOURCE,
        "browser": BROWSER_SOURCE,
    }[product]
    value = load(root, path, source)["version"]
    version_tuple(value)
    return value


def owned_files(product: str) -> list[str]:
    if product == "desktop":
        versions = [v.path for v in desktop.VERSION_FILES]
    elif product == "mobile":
        versions = list(MOBILE_FILES)
    else:
        versions = [BROWSER_SOURCE]
    return versions + [changelog_path(product), f".releases/state/{product}.json"]


def changelog_path(product: str) -> str:
    return {
        "desktop": "CHANGELOG.md",
        "mobile": "packages/mobile-contract/CHANGELOG.md",
        "browser": ".releases/changelogs/browser.md",
    }[product]


def legacy_commits(root: Path, source: str) -> list[tuple[str, str]]:
    # The first-parent adoption commit includes every old PR merged before the
    # policy became active, even if those PRs landed while this PR was in review.
    adoption = git(
        root,
        "log",
        "--first-parent",
        "--diff-filter=A",
        "--format=%H",
        source,
        "--",
        ".releases/config.json",
    ).splitlines()
    if not adoption:
        raise ValueError("Release policy must be committed before preparing a release")
    parents = git(root, "rev-list", "--parents", "-n", "1", adoption[-1]).split()
    if len(parents) < 2:
        return []
    end = parents[1]
    tags = git(
        root, "tag", "--merged", source, "--list", "v*", "--sort=-v:refname"
    ).splitlines()
    tag = next((t for t in tags if VERSION.fullmatch(t[1:])), None)
    return desktop._commits_in_range(root, f"{tag}..{end}" if tag else end)


def load_override(root: Path, product: str) -> dict[str, str] | None:
    path = f".releases/overrides/{product}.json"
    if not exists(root, path):
        return None
    value = load(root, path)
    if not isinstance(value, dict) or set(value) != {"baseline", "version", "reason"}:
        raise ValueError(f"Invalid override: {path}")
    if (
        version_tuple(value["version"]) <= version_tuple(value["baseline"])
        or not isinstance(value["reason"], str)
        or not value["reason"].strip()
    ):
        raise ValueError(f"Invalid override: {path}")
    return value


def plan(root: Path, product: str, source: str) -> dict[str, Any]:
    baseline = product_version(root, product, source)
    path = f".releases/state/{product}.json"
    state = (
        load(root, path, source)
        if exists(root, path, source)
        else {"version": baseline, "consumed": [], "legacy_complete": False}
    )
    if state["version"] != baseline:
        raise ValueError(f"{product}: release ledger does not match version files")
    notes = declarations(root, source)
    consumed = set(state["consumed"])
    if not consumed <= notes.keys():
        raise ValueError("Released declarations must not be deleted")
    pending = {
        p: n for p, n in notes.items() if p not in consumed and product in n["products"]
    }
    impact = max(
        (n["products"][product] for n in pending.values()), key=RANK.get, default="none"
    )
    legacy = (
        legacy_commits(root, source)
        if product == "desktop" and not state["legacy_complete"]
        else []
    )
    if legacy:
        old_impact, _ = desktop.infer_bump(legacy, baseline)
        user_visible = any(
            desktop.BREAKING_SUBJECT.match(s)
            or desktop.BREAKING_FOOTER.search(b)
            or (m := desktop.COMMIT_TYPE.match(s))
            and m.group(1).lower() in desktop.BUMP_BY_TYPE
            for s, b in legacy
        )
        if user_visible:
            impact = max((impact, old_impact), key=RANK.get)
    version = desktop.bump_semver(baseline, impact) if impact != "none" else baseline
    override = load_override(root, product)
    if override:
        if override["baseline"] == baseline:
            if version_tuple(override["version"]) <= version_tuple(baseline):
                raise ValueError("Override must advance the released version")
            version = override["version"]
        elif version_tuple(override["version"]) > version_tuple(baseline):
            raise ValueError("Override baseline is stale; review it before refreshing")
    return {
        "product": product,
        "baseline": baseline,
        "version": version,
        "releasable": version != baseline,
        "impact": impact,
        "pending": pending,
        "legacy": legacy,
        "state": {
            "version": version,
            "consumed": sorted(consumed | pending.keys()),
            "legacy_complete": True,
        },
    }


def render_notes(root: Path, data: dict[str, Any], source: str) -> str:
    product, version = data["product"], data["version"]
    path = changelog_path(product)
    existing = (
        read(root, path, source)
        if exists(root, path, source)
        else f"# {product.title()} changelog\n"
    )
    prefix = TAG_PREFIXES[product]
    draft = (
        desktop.generate_changelog_draft(
            version, root, subjects=[s for s, _ in data["legacy"]]
        )
        if data["legacy"]
        else f"## [v{version}]\n"
    )
    summaries = [
        n["summary"].strip()
        for n in data["pending"].values()
        if n["products"][product] != "none"
    ]
    if summaries:
        draft += "\n### Release notes\n" + "\n".join(f"- {s}" for s in summaries) + "\n"
    if not summaries and not data["legacy"]:
        draft += "\n### Release notes\n- Release maintenance\n"
    date = git(root, "show", "-s", "--format=%cs", source)
    draft = re.sub(r"^## .*", f"## [{prefix}{version}] - {date}", draft, count=1)
    if exists(root, path):
        current = read(root, path)
        match = re.search(
            rf"(?ms)^## \[{prefix}{re.escape(product_version(root, product))}\].*?(?=^## \[|\Z)",
            current,
        )
        if match and product_version(root, product) != data["baseline"]:
            highlights = desktop._extract_highlights(match.group())
            if highlights:
                draft = desktop._inject_highlights(draft, highlights)
    first = re.search(r"(?m)^## \[", existing)
    position = first.start() if first else len(existing.rstrip())
    return (
        existing[:position].rstrip()
        + "\n\n"
        + draft.rstrip()
        + "\n\n"
        + existing[position:].lstrip()
    )


def release_notes(root: Path, product: str) -> str:
    version = product_version(root, product)
    tag = TAG_PREFIXES[product] + version
    match = re.search(
        rf"(?ms)^## \[{re.escape(tag)}\][^\n]*\n.*?(?=^## \[|\Z)",
        read(root, changelog_path(product)),
    )
    if not match:
        raise ValueError(f"Missing changelog entry for {tag}")
    return match.group().strip() + "\n"


def apply(root: Path, product: str, source: str) -> dict[str, Any]:
    data = plan(root, product, source)
    if not data["releasable"]:
        return data
    notes = render_notes(root, data, source)
    if product == "desktop":
        with contextlib.redirect_stdout(io.StringIO()):
            for target in desktop.VERSION_FILES:
                desktop.write_version(root / target.path, target, data["version"])
    elif product == "mobile":
        mobile = load(root, MOBILE_SOURCE, source)
        mobile["version"] = data["version"]
        mobile["build"] += 1
        write(root, MOBILE_SOURCE, mobile)
        for path, content in version_outputs(root).items():
            path.write_text(content)
    else:
        manifest = load(root, BROWSER_SOURCE, source)
        manifest["version"] = data["version"]
        write(root, BROWSER_SOURCE, manifest)
    changelog = root / changelog_path(product)
    changelog.parent.mkdir(parents=True, exist_ok=True)
    changelog.write_text(notes, encoding="utf-8")
    write(root, f".releases/state/{product}.json", data["state"])
    return data


def affected_products(paths: list[str]) -> set[str]:
    affected = set()
    for path in paths:
        if (
            path.startswith("extensions/browser/")
            or path == "scripts/build_browser_extension.py"
        ):
            affected.add("browser")
        elif path.startswith(
            (
                "apps/ios/",
                "apps/android/",
                "packages/SuzentCore/",
                "packages/mobile-contract/",
            )
        ):
            affected.add("mobile")
        elif path.startswith(
            ("src/", "frontend/", "src-tauri/", "apps/suzent-installer/")
        ) or path in {"pyproject.toml", "uv.lock"}:
            affected.add("desktop")
        if path.startswith("packages/presentation/") or path in {
            "scripts/generate_presentation.py",
            "scripts/mobile_logo.py",
            "scripts/generate_app_icons.py",
            "scripts/generate_mobile_version.py",
        }:
            affected.update(("desktop", "mobile"))
    return affected


def check(
    root: Path, base: str | None = None, release_product: str | None = None
) -> None:
    if load(root, ".releases/config.json") != {"schema": 1}:
        raise ValueError("Unsupported release policy")
    notes = declarations(root)
    for product in PRODUCTS:
        load_override(root, product)
    if not base:
        return
    base = git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    before = declarations(root, base)
    for path, item in before.items():
        if notes.get(path) != item:
            raise ValueError(
                f"Merged declarations are immutable: {path}; correct an unreleased version with an override"
            )
    paths = git(root, "diff", "--name-only", base, "--").splitlines()
    if release_product:
        data = plan(root, release_product, base)
        if (
            not data["releasable"]
            or product_version(root, release_product) != data["version"]
        ):
            raise ValueError("Release version differs from the reviewed plan")
        if load(root, f".releases/state/{release_product}.json") != data["state"]:
            raise ValueError("Release ledger differs from the reviewed plan")
        if read(root, changelog_path(release_product)) != render_notes(
            root, data, base
        ):
            raise ValueError(
                "Release notes differ from the plan; use a highlights block for editorial text"
            )
        if release_product == "desktop":
            if any(
                desktop.read_version(root / v.path, v) != data["version"]
                for v in desktop.VERSION_FILES
            ):
                raise ValueError("Desktop version files are not synchronized")
        elif release_product == "mobile":
            mobile = load(root, MOBILE_SOURCE, base)
            mobile["version"] = data["version"]
            mobile["build"] += 1
            if load(root, MOBILE_SOURCE) != mobile or any(
                path.read_text() != content
                for path, content in version_outputs(root).items()
            ):
                raise ValueError("Mobile version/build files are not synchronized")
        else:
            manifest = load(root, BROWSER_SOURCE, base)
            manifest["version"] = data["version"]
            if load(root, BROWSER_SOURCE) != manifest:
                raise ValueError(
                    "Browser release must only update the manifest version"
                )
        allowed = set(owned_files(release_product)) | {
            f".releases/overrides/{release_product}.json"
        }
        if release_product == "desktop":
            allowed.add(".release-assets-mode")
        if set(paths) - allowed:
            raise ValueError(
                f"Unexpected changes in release PR: {sorted(set(paths) - allowed)}"
            )
        return
    if any(p.startswith(".releases/state/") for p in paths):
        raise ValueError("Only release PRs may change the consumed-declaration ledger")
    declared = set().union(
        *(set(n["products"]) for p, n in notes.items() if p not in before)
    )
    missing = affected_products(paths) - declared
    if missing:
        raise ValueError(
            f"Add a release declaration for: {', '.join(sorted(missing))}; use none with a reason when no release is needed"
        )
    for product in PRODUCTS:
        if product_version(root, product) != product_version(root, product, base):
            raise ValueError(
                "Change product versions through a release PR, not a feature PR"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("check", "plan", "apply", "files", "override", "notes")
    )
    parser.add_argument("--product", choices=PRODUCTS, default="desktop")
    parser.add_argument("--source", default="HEAD")
    parser.add_argument("--base")
    parser.add_argument("--release-product", choices=PRODUCTS)
    parser.add_argument("--version")
    parser.add_argument("--reason")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.command == "check":
            check(root, args.base, args.release_product)
        elif args.command == "notes":
            print(release_notes(root, args.product), end="")
        elif args.command == "files":
            print("\n".join(owned_files(args.product)))
        elif args.command == "override":
            baseline = product_version(root, args.product, args.source)
            value = (
                desktop.bump_semver(baseline, args.version)
                if args.version in {"patch", "minor", "major"}
                else args.version
            )
            if version_tuple(value) <= version_tuple(baseline) or not args.reason:
                raise ValueError("Override requires a newer version and a reason")
            write(
                root,
                f".releases/overrides/{args.product}.json",
                {"baseline": baseline, "version": value, "reason": args.reason},
            )
        else:
            print(
                json.dumps(
                    (apply if args.command == "apply" else plan)(
                        root, args.product, args.source
                    ),
                    ensure_ascii=False,
                )
            )
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Release plan error: {error}") from error


if __name__ == "__main__":
    main()
