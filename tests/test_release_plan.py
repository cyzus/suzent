"""Release behavior across real Git snapshots, refreshes, and independent products."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release_plan.py"
spec = importlib.util.spec_from_file_location("suzent_release_plan", SCRIPT)
assert spec is not None and spec.loader is not None
release = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(SCRIPT.parent))
try:
    spec.loader.exec_module(release)
finally:
    sys.path.pop(0)


def commit(root: Path, subject: str = "chore: test snapshot") -> str:
    release.git(root, "add", ".")
    release.git(root, "commit", "-m", subject)
    return release.git(root, "rev-parse", "HEAD")


def note(root: Path, name: str, **products: str) -> None:
    release.write(
        root,
        f".releases/changes/{name}.json",
        {
            "products": products,
            "summary": name,
            "reason": "Tested maintenance decision",
        },
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    release.git(tmp_path, "init", "-b", "main")
    release.git(tmp_path, "config", "user.name", "Release Test")
    release.git(tmp_path, "config", "user.email", "release@example.invalid")
    release.write(tmp_path, "src-tauri/tauri.conf.json", {"version": "0.14.0"})
    release.write(tmp_path, release.MOBILE_SOURCE, {"version": "0.1.0", "build": 7})
    release.write(
        tmp_path,
        release.BROWSER_SOURCE,
        {"version": "0.1.2", "manifest_version": 3, "name": "Suzent"},
    )
    (tmp_path / "apps/ios/Config").mkdir(parents=True)
    (tmp_path / "apps/android").mkdir(parents=True)
    for path, content in release.version_outputs(tmp_path).items():
        path.write_text(content)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [v0.14.0] - 2026-01-01\n\n- Published history\n"
    )
    monkeypatch.setattr(
        release.desktop,
        "VERSION_FILES",
        (release.desktop.VersionFile("src-tauri/tauri.conf.json", "json"),),
    )
    commit(tmp_path)
    release.git(tmp_path, "tag", "v0.14.0")
    return tmp_path


def adopt(root: Path) -> str:
    release.write(root, ".releases/config.json", {"schema": 1})
    return commit(root, "ci: adopt release declarations")


def test_mobile_only_does_not_bump_desktop(repo: Path) -> None:
    adopt(repo)
    note(repo, "mobile-feature", mobile="minor")
    source = commit(repo, "feat(mobile): feature")
    assert not release.plan(repo, "desktop", source)["releasable"]
    assert release.plan(repo, "mobile", source)["version"] == "0.2.0"


def test_shared_change_has_independent_impacts(repo: Path) -> None:
    adopt(repo)
    note(repo, "shared", mobile="minor", desktop="patch")
    source = commit(repo, "feat: shared change")
    assert release.plan(repo, "desktop", source)["version"] == "0.14.1"
    assert release.plan(repo, "mobile", source)["version"] == "0.2.0"


def test_highest_impact_wins_and_explicit_major_can_reach_one(repo: Path) -> None:
    adopt(repo)
    note(repo, "fix-a", mobile="patch")
    note(repo, "fix-b", mobile="patch")
    note(repo, "feature", mobile="minor")
    source = commit(repo)
    assert release.plan(repo, "mobile", source)["version"] == "0.2.0"
    note(repo, "stable", mobile="major")
    source = commit(repo)
    assert release.plan(repo, "mobile", source)["version"] == "1.0.0"


def test_legacy_unreleased_commits_are_preserved_once(repo: Path) -> None:
    (repo / "old.txt").write_text("old feature")
    commit(repo, "feat: legacy feature")
    adopt(repo)
    source = release.git(repo, "rev-parse", "HEAD")
    assert release.plan(repo, "desktop", source)["version"] == "0.15.0"
    release.apply(repo, "desktop", source)
    shipped = commit(repo, "chore: release v0.15.0")
    # The ledger closes the tag-creation race: no new PR even before tagging.
    assert not release.plan(repo, "desktop", shipped)["releasable"]
    note(repo, "new-fix", desktop="patch")
    source = commit(repo)
    assert release.plan(repo, "desktop", source)["version"] == "0.15.1"


def test_legacy_patch_is_releasable(repo: Path) -> None:
    (repo / "fix.txt").write_text("fixed")
    commit(repo, "fix: legacy patch")
    source = adopt(repo)
    assert release.plan(repo, "desktop", source)["version"] == "0.14.1"


def test_legacy_follows_main_parent_when_adoption_is_merge_commit(repo: Path) -> None:
    release.git(repo, "switch", "-c", "policy")
    adopt(repo)
    release.git(repo, "switch", "main")
    (repo / "late.txt").write_text("arrived during policy review")
    commit(repo, "feat: late legacy change")
    release.git(repo, "merge", "--no-ff", "policy", "-m", "Merge policy")
    assert release.plan(repo, "desktop", "HEAD")["version"] == "0.15.0"


def test_refresh_is_idempotent_and_product_consumption_is_independent(
    repo: Path,
) -> None:
    adopt(repo)
    note(repo, "shared", desktop="patch", mobile="minor")
    source = commit(repo)
    release.apply(repo, "mobile", source)
    first = {p: (repo / p).read_bytes() for p in release.owned_files("mobile")}
    release.apply(repo, "mobile", source)
    assert first == {p: (repo / p).read_bytes() for p in release.owned_files("mobile")}
    assert release.load(repo, release.MOBILE_SOURCE)["build"] == 8
    shipped = commit(repo)
    assert not release.plan(repo, "mobile", shipped)["releasable"]
    assert release.plan(repo, "desktop", shipped)["version"] == "0.14.1"
    assert "shared" in (repo / release.changelog_path("mobile")).read_text()


def test_override_survives_new_main_commits_and_expires_after_release(
    repo: Path,
) -> None:
    adopt(repo)
    note(repo, "mobile", mobile="patch")
    source = commit(repo)
    release.write(
        repo,
        ".releases/overrides/mobile.json",
        {
            "baseline": "0.1.0",
            "version": "0.3.0",
            "reason": "Reviewed product milestone",
        },
    )
    release.apply(repo, "mobile", source)
    # Simulate main advancing without importing pending version files.
    release.git(repo, "stash", "push", "-u")
    note(repo, "new-feature", mobile="minor")
    source = commit(repo)
    release.git(repo, "stash", "pop")
    release.apply(repo, "mobile", source)
    assert release.product_version(repo, "mobile") == "0.3.0"
    assert "new-feature" in (repo / release.changelog_path("mobile")).read_text()
    commit(repo)
    assert not release.plan(repo, "mobile", "HEAD")["releasable"]
    note(repo, "followup", mobile="patch")
    source = commit(repo)
    assert release.plan(repo, "mobile", source)["version"] == "0.3.1"


def test_refresh_preserves_highlights_and_published_history(repo: Path) -> None:
    adopt(repo)
    note(repo, "first", desktop="patch")
    source = commit(repo)
    release.apply(repo, "desktop", source)
    path = repo / "CHANGELOG.md"
    path.write_text(
        path.read_text().replace(
            "### Release notes",
            "<!-- highlights -->\nReviewed summary\n<!-- /highlights -->\n\n### Release notes",
        )
    )
    release.apply(repo, "desktop", source)
    assert path.read_text().count("Reviewed summary") == 1
    assert path.read_text().count("Published history") == 1
    assert path.read_text().count("## [v0.14.1]") == 1


@pytest.mark.parametrize(
    "change",
    [
        {"products": {"android": "minor"}, "summary": "x"},
        {"products": {"mobile": "feature"}, "summary": "x"},
        {"products": {"mobile": True}, "summary": "x"},
        {"products": {"mobile": "none"}, "summary": "x"},
        {"products": {"mobile": "patch"}, "summary": ""},
        {"products": {}, "summary": "x"},
    ],
)
def test_invalid_declarations_fail(repo: Path, change: dict) -> None:
    adopt(repo)
    release.write(repo, ".releases/changes/invalid.json", change)
    with pytest.raises(ValueError):
        release.check(repo)


def test_no_release_requires_explicit_reason_for_app_changes(repo: Path) -> None:
    base = adopt(repo)
    path = repo / "apps/android/example.kt"
    path.write_text("// existing feature implementation")
    release.git(repo, "add", ".")
    with pytest.raises(ValueError, match="mobile"):
        release.check(repo, base)
    note(repo, "internal-refactor", mobile="none")
    release.check(repo, base)
    commit(repo, "feat: misleading title")
    assert not release.plan(repo, "mobile", "HEAD")["releasable"]


def test_docs_need_no_declaration_and_merged_notes_are_immutable(repo: Path) -> None:
    adopt(repo)
    note(repo, "fix", mobile="patch")
    base = commit(repo)
    (repo / "README.md").write_text("documentation")
    release.check(repo, base)
    note(repo, "fix", mobile="minor")
    with pytest.raises(ValueError, match="immutable"):
        release.check(repo, base)


def test_release_validation_rejects_tampered_ledger_and_unrelated_changes(
    repo: Path,
) -> None:
    adopt(repo)
    note(repo, "fix", mobile="patch")
    base = commit(repo)
    release.apply(repo, "mobile", base)
    release.git(repo, "add", ".")
    release.check(repo, base, "mobile")
    (repo / "README.md").write_text("unexpected")
    release.git(repo, "add", ".")
    with pytest.raises(ValueError, match="Unexpected"):
        release.check(repo, base, "mobile")
    release.git(repo, "rm", "-f", "README.md")
    data = release.load(repo, ".releases/state/mobile.json")
    data["consumed"] = []
    release.write(repo, ".releases/state/mobile.json", data)
    with pytest.raises(ValueError, match="ledger"):
        release.check(repo, base, "mobile")


def test_normal_pr_cannot_manually_bump_version(repo: Path) -> None:
    base = adopt(repo)
    note(repo, "manual", mobile="patch")
    release.write(repo, release.MOBILE_SOURCE, {"version": "0.2.0", "build": 7})
    with pytest.raises(ValueError, match="release PR"):
        release.check(repo, base)


def test_docs_only_legacy_and_none_declarations_do_not_open_release(repo: Path) -> None:
    (repo / "README.md").write_text("legacy docs")
    commit(repo, "docs: old documentation")
    adopt(repo)
    note(repo, "tooling", desktop="none", mobile="none")
    source = commit(repo, "feat: title does not control a release")
    assert not release.plan(repo, "desktop", source)["releasable"]
    assert not release.plan(repo, "mobile", source)["releasable"]


def test_declared_patch_beats_new_feat_commit_title(repo: Path) -> None:
    adopt(repo)
    note(repo, "reviewed-impact", desktop="patch")
    source = commit(repo, "feat: developer description")
    assert release.plan(repo, "desktop", source)["version"] == "0.14.1"


def test_shared_presentation_requires_both_product_decisions(repo: Path) -> None:
    base = adopt(repo)
    release.write(repo, "packages/presentation/tokens.json", {"spacing": 4})
    release.git(repo, "add", ".")
    note(repo, "mobile-only", mobile="patch")
    with pytest.raises(ValueError, match="desktop"):
        release.check(repo, base)
    note(repo, "desktop-too", desktop="patch")
    release.check(repo, base)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"baseline": "0.1.0", "version": "0.1.0", "reason": "same version"},
        {"baseline": "0.1.0", "version": "0.0.1", "reason": "downgrade"},
        {"baseline": "0.1.0", "version": "0.2.0", "reason": ""},
        {"baseline": "0.1.0", "version": "0.2", "reason": "bad version"},
    ],
)
def test_invalid_override_is_rejected(repo: Path, value: dict[str, str]) -> None:
    adopt(repo)
    release.write(repo, ".releases/overrides/mobile.json", value)
    with pytest.raises(ValueError):
        release.check(repo)


def test_mobile_release_rejects_build_number_drift(repo: Path) -> None:
    adopt(repo)
    note(repo, "fix", mobile="patch")
    base = commit(repo)
    release.apply(repo, "mobile", base)
    value = release.load(repo, release.MOBILE_SOURCE)
    value["build"] += 1
    release.write(repo, release.MOBILE_SOURCE, value)
    for path, content in release.version_outputs(repo).items():
        path.write_text(content)
    with pytest.raises(ValueError, match="build"):
        release.check(repo, base, "mobile")


def test_release_cannot_rewrite_published_changelog(repo: Path) -> None:
    adopt(repo)
    note(repo, "fix", desktop="patch")
    base = commit(repo)
    release.apply(repo, "desktop", base)
    path = repo / "CHANGELOG.md"
    path.write_text(path.read_text().replace("Published history", "Rewritten history"))
    with pytest.raises(ValueError, match="notes"):
        release.check(repo, base, "desktop")


def test_invalid_note_extension_is_rejected_before_release(repo: Path) -> None:
    adopt(repo)
    release.write(repo, ".releases/changes/wrong.yaml", {"mobile": "patch"})
    with pytest.raises(ValueError, match="filename"):
        release.check(repo)


def test_browser_only_release_leaves_desktop_and_mobile_unchanged(repo: Path) -> None:
    adopt(repo)
    note(repo, "browser-fix", browser="patch")
    source = commit(repo, "feat(browser): title is not the release decision")
    other_versions = {
        p: release.product_version(repo, p) for p in ("desktop", "mobile")
    }
    assert not release.plan(repo, "desktop", source)["releasable"]
    assert not release.plan(repo, "mobile", source)["releasable"]
    data = release.apply(repo, "browser", source)
    assert data["version"] == "0.1.3"
    assert other_versions == {
        p: release.product_version(repo, p) for p in other_versions
    }
    assert release.load(repo, release.BROWSER_SOURCE) == {
        "version": "0.1.3",
        "manifest_version": 3,
        "name": "Suzent",
    }
    files = {p: (repo / p).read_bytes() for p in release.owned_files("browser")}
    release.apply(repo, "browser", source)
    assert files == {p: (repo / p).read_bytes() for p in release.owned_files("browser")}
    release.git(repo, "add", ".")
    release.check(repo, source, "browser")
    shipped = commit(repo)
    assert not release.plan(repo, "browser", shipped)["releasable"]


def test_browser_app_pr_declares_impact_without_manifest_bump(repo: Path) -> None:
    base = adopt(repo)
    (repo / "extensions/browser/worker.js").write_text("// updated worker")
    release.git(repo, "add", ".")
    with pytest.raises(ValueError, match="browser"):
        release.check(repo, base)
    note(repo, "worker-fix", browser="patch")
    release.check(repo, base)
    release.write(repo, release.BROWSER_SOURCE, {"version": "0.1.3"})
    with pytest.raises(ValueError, match="release PR"):
        release.check(repo, base)


def test_browser_and_desktop_consume_shared_change_independently(repo: Path) -> None:
    adopt(repo)
    note(repo, "native-host", browser="minor", desktop="patch")
    source = commit(repo)
    release.apply(repo, "browser", source)
    shipped = commit(repo)
    assert not release.plan(repo, "browser", shipped)["releasable"]
    assert release.plan(repo, "desktop", shipped)["version"] == "0.14.1"
    release.apply(repo, "desktop", shipped)
    shipped = commit(repo)
    assert not release.plan(repo, "desktop", shipped)["releasable"]
    assert not release.plan(repo, "browser", shipped)["releasable"]
    assert not release.plan(repo, "mobile", shipped)["releasable"]


def test_browser_release_cannot_change_permissions(repo: Path) -> None:
    adopt(repo)
    note(repo, "fix", browser="patch")
    base = commit(repo)
    release.apply(repo, "browser", base)
    manifest = release.load(repo, release.BROWSER_SOURCE)
    manifest["permissions"] = ["debugger"]
    release.write(repo, release.BROWSER_SOURCE, manifest)
    with pytest.raises(ValueError, match="only update the manifest version"):
        release.check(repo, base, "browser")


def test_browser_notes_are_version_scoped_and_outside_package(repo: Path) -> None:
    adopt(repo)
    note(repo, "first-browser-fix", browser="patch")
    base = commit(repo)
    release.apply(repo, "browser", base)
    commit(repo)
    note(repo, "second-browser-fix", browser="patch")
    base = commit(repo)
    release.apply(repo, "browser", base)
    text = release.release_notes(repo, "browser")
    assert "browser-v0.1.4" in text
    assert "second-browser-fix" in text
    assert "first-browser-fix" not in text
    assert not release.changelog_path("browser").startswith("extensions/browser/")


def test_browser_override_is_independent(repo: Path) -> None:
    adopt(repo)
    note(repo, "browser-feature", browser="minor")
    base = commit(repo)
    release.write(
        repo,
        ".releases/overrides/browser.json",
        {
            "baseline": "0.1.2",
            "version": "0.3.0",
            "reason": "Reviewed browser milestone",
        },
    )
    release.apply(repo, "browser", base)
    assert release.product_version(repo, "browser") == "0.3.0"
    assert release.product_version(repo, "desktop") == "0.14.0"
    assert release.product_version(repo, "mobile") == "0.1.0"
    release.apply(repo, "browser", base)
    assert release.product_version(repo, "browser") == "0.3.0"
    shipped = commit(repo)
    assert not release.plan(repo, "browser", shipped)["releasable"]


def test_browser_plan_packages_new_version_without_release_metadata(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import zipfile

    builder_spec = importlib.util.spec_from_file_location(
        "browser_builder", SCRIPT.with_name("build_browser_extension.py")
    )
    assert builder_spec is not None and builder_spec.loader is not None
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "EXTENSION", repo / "extensions/browser")
    for name in ("worker.js", "pair.js", "popup.html"):
        (builder.EXTENSION / name).write_text("fixture")
    adopt(repo)
    note(repo, "browser-package", browser="patch")
    source = commit(repo)
    release.apply(repo, "browser", source)
    first = builder.build(repo / "first.zip")
    second = builder.build(repo / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == "0.1.3"
        assert set(archive.namelist()) == {
            "manifest.json",
            "worker.js",
            "pair.js",
            "popup.html",
        }
