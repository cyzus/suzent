import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


def load_bump_version_module() -> ModuleType:
    script_path = Path(__file__).resolve().parent.parent / "scripts/bump_version.py"
    spec = importlib.util.spec_from_file_location("suzent_bump_version", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bump_version = load_bump_version_module()
VERSION_FILES = bump_version.VERSION_FILES
VersionFile = bump_version.VersionFile
bump_semver = bump_version.bump_semver
generate_changelog_draft = bump_version.generate_changelog_draft
read_version = bump_version.read_version
write_version = bump_version.write_version
git_subjects_since_last_release = bump_version._git_subjects_since_last_release
replace_changelog_entry = bump_version._replace_changelog_entry
retitle_changelog_entry = bump_version._retitle_changelog_entry
update_changelog = bump_version.update_changelog
infer_bump = bump_version.infer_bump


@pytest.mark.parametrize(
    ("bump_type", "expected"),
    [
        ("patch", "1.2.4"),
        ("minor", "1.3.0"),
        ("major", "2.0.0"),
    ],
)
def test_bump_semver(bump_type: str, expected: str) -> None:
    assert bump_semver("1.2.3", bump_type) == expected


def test_version_files_cover_main_app_and_installer() -> None:
    paths = {target.path for target in VERSION_FILES}

    assert "pyproject.toml" in paths
    assert "src-tauri/Cargo.lock" in paths
    assert "apps/suzent-installer/package.json" in paths
    assert "apps/suzent-installer/Cargo.lock" in paths


def test_package_lock_updates_both_project_versions(tmp_path: Path) -> None:
    path = tmp_path / "package-lock.json"
    path.write_text(
        json.dumps(
            {
                "name": "example",
                "version": "0.1.0",
                "packages": {"": {"name": "example", "version": "0.1.0"}},
            }
        ),
        encoding="utf-8",
    )
    target = VersionFile("package-lock.json", "package-lock")

    write_version(path, target, "0.2.0")

    assert read_version(path, target) == "0.2.0"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["packages"][""]["version"] == "0.2.0"


def test_named_lock_updates_only_selected_package(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.lock"
    path.write_text(
        '[[package]]\nname = "dependency"\nversion = "9.9.9"\n\n'
        '[[package]]\nname = "suzent-installer"\nversion = "0.6.6"\n',
        encoding="utf-8",
    )
    target = VersionFile("Cargo.lock", "named-lock", "suzent-installer")

    write_version(path, target, "0.7.1")

    content = path.read_text(encoding="utf-8")
    assert 'name = "dependency"\nversion = "9.9.9"' in content
    assert read_version(path, target) == "0.7.1"


def test_changelog_accepts_scopes_and_keeps_unprefixed_changes(
    tmp_path: Path,
) -> None:
    draft = generate_changelog_draft(
        "1.0.0",
        tmp_path,
        subjects=[
            "feat(ui): add update controls",
            "fix: avoid release race",
            "Improve desktop packaging",
            "docs: refresh release guide",
        ],
    )

    assert "- Add update controls" in draft
    assert "- Avoid release race" in draft
    assert "- Improve desktop packaging" in draft
    assert "refresh release guide" not in draft


def test_changelog_uses_reachable_release_commit_when_tag_diverged(
    tmp_path: Path,
) -> None:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.name", "Suzent Test")
    git("config", "user.email", "test@suzent.local")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    git("add", "CHANGELOG.md")
    git("commit", "-m", "initial")
    base_commit = git("rev-parse", "HEAD")

    changelog.write_text(
        "# Changelog\n\n## [v1.0.0] - 2026-07-01\n",
        encoding="utf-8",
    )
    git("add", "CHANGELOG.md")
    git("commit", "-m", "chore: release v1.0.0")
    git("tag", "v1.0.0")

    git("switch", "--detach", base_commit)
    changelog.write_text(
        "# Changelog\n\n## [v1.0.0] - 2026-07-02\n",
        encoding="utf-8",
    )
    git("add", "CHANGELOG.md")
    git("commit", "-m", "chore: release v1.0.0")
    (tmp_path / "feature.txt").write_text("new\n", encoding="utf-8")
    git("add", "feature.txt")
    git("commit", "-m", "feat: only new change")

    assert git_subjects_since_last_release(tmp_path, "1.0.1") == [
        "feat: only new change"
    ]

    current = changelog.read_text(encoding="utf-8")
    changelog.write_text(
        "# Changelog\n\n"
        "## [v1.0.1] - 2026-07-03\n\n"
        "### ⚡ Changed\n"
        "- Stale draft\n\n" + current.removeprefix("# Changelog\n\n"),
        encoding="utf-8",
    )

    assert update_changelog(tmp_path, "1.0.1", replace_existing=True)
    refreshed = changelog.read_text(encoding="utf-8")
    assert "Stale draft" not in refreshed
    assert "- Only new change" in refreshed


def test_refresh_changelog_replaces_only_current_version() -> None:
    existing = (
        "# Changelog\n\n"
        "## [v1.0.1] - 2026-07-02\n\n"
        "### ⚡ Changed\n"
        "- Stale draft\n\n"
        "## [v1.0.0] - 2026-07-01\n\n"
        "### 🚀 Added\n"
        "- Previous release\n"
    )
    draft = "## [v1.0.1] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    refreshed = replace_changelog_entry(existing, "1.0.1", draft)

    assert refreshed is not None
    assert "Stale draft" not in refreshed
    assert "- Current draft" in refreshed
    assert "- Previous release" in refreshed


def test_changelog_cli_uses_utf8_when_console_defaults_to_gbk() -> None:
    root = Path(__file__).resolve().parent.parent
    environment = {**os.environ, "PYTHONIOENCODING": "gbk"}

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/bump_version.py"),
            "patch",
            "--changelog",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    output = result.stdout.decode("utf-8")
    assert any(marker in output for marker in ("🚀", "⚡", "🐛"))


def test_a_feature_outranks_a_fix() -> None:
    """The highest-ranking commit in the range sets the bump, not the last one."""
    commits = [("fix(memory): stop a re-render", ""), ("feat(ui): add a panel", "")]

    assert infer_bump(commits, "1.2.3")[0] == "minor"


def test_only_fixes_stay_a_patch() -> None:
    commits = [("fix: one", ""), ("perf: two", "")]

    assert infer_bump(commits, "1.2.3")[0] == "patch"


def test_a_breaking_change_before_1_0_does_not_declare_stability() -> None:
    """0.9.1 plus a breaking change is 0.10.0. Reaching 1.0.0 stays deliberate."""
    commits = [("feat!: drop the legacy key bundle", "")]

    bump, reason = infer_bump(commits, "0.9.1")

    assert bump == "minor"
    assert "pre-1.0" in reason


def test_a_breaking_change_after_1_0_is_major() -> None:
    commits = [("feat!: drop the legacy key bundle", "")]

    assert infer_bump(commits, "1.4.0")[0] == "major"


def test_a_breaking_change_footer_counts_as_breaking() -> None:
    """Not every breaking commit marks its subject with `!`."""
    commits = [("feat: rework the secret backend", "BREAKING CHANGE: bundles are gone")]

    assert infer_bump(commits, "1.4.0")[0] == "major"


def test_invisible_work_alone_is_a_maintenance_patch() -> None:
    """refactor/docs/chore earn no bump, but a requested release still ships."""
    commits = [
        ("refactor: tidy", ""),
        ("docs: fix a typo", ""),
        ("chore: bump deps", ""),
    ]

    bump, reason = infer_bump(commits, "1.2.3")

    assert bump == "patch"
    assert "maintenance" in reason


def test_auto_resolves_to_a_concrete_version(tmp_path: Path) -> None:
    """`auto` is what the workflow passes; it must reach a real version string."""
    commits = [("feat: something", "")]
    monkey = bump_version._git_commits_since_last_release
    bump_version._git_commits_since_last_release = lambda root, version: commits
    try:
        assert (
            bump_version.parse_version_argument("0.9.1", "auto", tmp_path) == "0.10.0"
        )
    finally:
        bump_version._git_commits_since_last_release = monkey


def _release_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A repo shaped like an open release PR: tagged v0.9.1, files bumped to 0.9.2."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()

    conf = tmp_path / "src-tauri" / "tauri.conf.json"
    conf.parent.mkdir(parents=True)
    monkeypatch.setattr(
        bump_version,
        "VERSION_FILES",
        (VersionFile("src-tauri/tauri.conf.json", "json"),),
    )

    git("init")
    git("config", "user.name", "Suzent Test")
    git("config", "user.email", "test@suzent.local")

    conf.write_text(json.dumps({"version": "0.9.1"}) + "\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [v0.9.1] - 2026-08-22\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-m", "chore: release v0.9.1")
    git("tag", "v0.9.1")
    return git, conf


def test_reconcile_promotes_a_patch_once_a_feature_lands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The always-open release PR bug: opened on a fix, then a feat merges in.

    Shipping that as a patch is exactly what deriving the bump exists to stop,
    so the pending version has to be re-derived rather than frozen at open time.
    """
    git, conf = _release_repo(tmp_path, monkeypatch)

    # The release PR opens as a patch.
    conf.write_text(json.dumps({"version": "0.9.2"}) + "\n", encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text(encoding="utf-8").replace(
            "## [v0.9.1]",
            "## [v0.9.2] - 2026-08-24\n\n### 🐛 Fixed\n- A fix\n\n## [v0.9.1]",
        ),
        encoding="utf-8",
    )
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "fix: a fix")

    # Then a feature merges into main and gets pulled into the release branch.
    (tmp_path / "b.txt").write_text("y\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "feat: a feature")

    old, new, reason = bump_version.reconcile_version(tmp_path)

    assert (old, new) == ("0.9.2", "0.10.0")
    assert "feat: a feature" in reason
    assert json.loads(conf.read_text(encoding="utf-8"))["version"] == "0.10.0"
    assert "## [v0.10.0]" in changelog.read_text(encoding="utf-8")
    assert "## [v0.9.2]" not in changelog.read_text(encoding="utf-8")


def test_reconcile_does_not_compound_the_pending_bump(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runs on every push to main, so it must be idempotent.

    The baseline is the last tagged release, never the version already written
    into the release branch — using the latter would climb a minor per push.
    """
    git, conf = _release_repo(tmp_path, monkeypatch)

    conf.write_text(json.dumps({"version": "0.9.2"}) + "\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "feat: a feature")

    first = bump_version.reconcile_version(tmp_path)[1]
    second = bump_version.reconcile_version(tmp_path)[1]
    third = bump_version.reconcile_version(tmp_path)[1]

    assert first == second == third == "0.10.0"


def test_last_release_tag_ignores_an_untagged_pending_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git, _ = _release_repo(tmp_path, monkeypatch)

    assert bump_version.last_release_tag(tmp_path) == "v0.9.1"


PENDING_WITH_HIGHLIGHTS = (
    "# Changelog\n\n"
    "## [v1.1.0] - 2026-07-02\n\n"
    "<!-- highlights -->\n"
    "Memory is the story of this release: claims now expire, and the\n"
    "vault stops losing facts on restart.\n"
    "<!-- /highlights -->\n\n"
    "### ⚡ Changed\n"
    "- Stale draft\n\n"
    "## [v1.0.0] - 2026-07-01\n\n"
    "### 🚀 Added\n"
    "- Previous release\n"
)


def test_refresh_preserves_hand_written_highlights() -> None:
    draft = "## [v1.1.0] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    refreshed = replace_changelog_entry(PENDING_WITH_HIGHLIGHTS, "1.1.0", draft)

    assert refreshed is not None
    # The generated body is rebuilt from scratch...
    assert "Stale draft" not in refreshed
    assert "- Current draft" in refreshed
    # ...but the prose written on the release PR survives it.
    assert "Memory is the story of this release" in refreshed
    assert "vault stops losing facts on restart." in refreshed
    assert "- Previous release" in refreshed


def test_highlights_sit_directly_under_the_heading() -> None:
    draft = "## [v1.1.0] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    refreshed = replace_changelog_entry(PENDING_WITH_HIGHLIGHTS, "1.1.0", draft)

    assert refreshed is not None
    lines = refreshed.split("\n")
    heading = lines.index("## [v1.1.0] - 2026-07-03")
    assert lines[heading + 1] == ""
    assert lines[heading + 2] == "<!-- highlights -->"
    # The generated sections come after the preserved block, not before it.
    assert lines.index("### 🐛 Fixed") > lines.index("<!-- /highlights -->")


def test_refreshing_twice_leaves_the_highlights_alone() -> None:
    draft = "## [v1.1.0] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    once = replace_changelog_entry(PENDING_WITH_HIGHLIGHTS, "1.1.0", draft)
    assert once is not None
    twice = replace_changelog_entry(once, "1.1.0", draft)

    # Without this, every push to main would nest another copy of the block.
    assert twice == once
    assert once.count("<!-- highlights -->") == 1


def test_highlights_survive_a_retitle_when_the_bump_grows(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(PENDING_WITH_HIGHLIGHTS, encoding="utf-8")

    # A `feat` merging into a patch release PR promotes 1.0.1 -> 1.1.0; here the
    # pending entry is renamed the same way the reconcile renames it.
    retitle_changelog_entry(tmp_path, "1.1.0", "2.0.0")
    renamed = changelog.read_text(encoding="utf-8")
    assert "## [v2.0.0]" in renamed

    draft = "## [v2.0.0] - 2026-07-03\n\n### 🚀 Added\n- Breaking change\n"
    refreshed = replace_changelog_entry(renamed, "2.0.0", draft)

    assert refreshed is not None
    assert "Memory is the story of this release" in refreshed


def test_entry_without_highlights_is_replaced_wholesale() -> None:
    existing = (
        "# Changelog\n\n## [v1.1.0] - 2026-07-02\n\n### ⚡ Changed\n- Stale draft\n"
    )
    draft = "## [v1.1.0] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    refreshed = replace_changelog_entry(existing, "1.1.0", draft)

    assert refreshed is not None
    assert "highlights" not in refreshed
    assert "Stale draft" not in refreshed


def test_an_unclosed_highlights_block_is_not_preserved() -> None:
    # Better to lose an unterminated block than to swallow the whole entry into
    # it and stop regenerating the release notes.
    existing = (
        "# Changelog\n\n"
        "## [v1.1.0] - 2026-07-02\n\n"
        "<!-- highlights -->\n"
        "Someone forgot the closing marker.\n\n"
        "### ⚡ Changed\n"
        "- Stale draft\n"
    )
    draft = "## [v1.1.0] - 2026-07-03\n\n### 🐛 Fixed\n- Current draft\n"

    refreshed = replace_changelog_entry(existing, "1.1.0", draft)

    assert refreshed is not None
    assert "Someone forgot" not in refreshed
    assert "- Current draft" in refreshed
