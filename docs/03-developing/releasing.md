# Release Guide

Suzent uses a Release PR workflow. Preparing a release is a single manual
action; version synchronization, tagging, cross-platform builds, and GitHub
Release publication are automated.

## Normal release

1. Open **Actions → Prepare Release → Run workflow**.
2. Enter `patch`, `minor`, `major`, or an exact version such as `0.8.0`.
3. Review the generated `release/vX.Y.Z` pull request. Edit the generated
   changelog entry if needed, wait for required checks, and merge it.
4. The merge automatically creates the `vX.Y.Z` tag and starts
   **Build and Publish Desktop Release**.
5. Verify the published release and its assets on the
   [Releases page](https://github.com/cyzus/suzent/releases).

The release remains a draft while Windows, macOS Intel, macOS Apple Silicon,
and Linux builds run. It is published only after every build succeeds. A failed
build therefore cannot expose a partially populated release.

### If main changes before merge

Do not merge a stale Release PR. Open
**Actions → Refresh Release PR → Run workflow**, enter the PR number, and wait
for the refreshed CI run.

The refresh workflow merges the latest `main` into the release branch,
regenerates the current version's changelog section, validates every version
source, pushes the result, and explicitly starts CI. Review the regenerated
notes again before merging because refresh replaces any manual edits in that
version's section.

The post-merge workflow independently verifies that the Release PR head
contained the latest pre-merge `main` commit. If it did not, tag creation and
publication stop instead of releasing code that is missing from the notes.

## What is automated

`scripts/bump_version.py` synchronizes the version in:

- the Python project and `uv.lock`;
- the frontend and desktop npm manifests and lock files;
- the main Tauri configuration, Cargo manifest, and Cargo lock;
- the standalone installer's Tauri, npm, and Cargo files.

It also generates a changelog draft from commits since the last tag. Scoped
conventional commits such as `feat(ui): ...` are categorized, while unprefixed
commit subjects are retained under **Changed** so release notes are not silently
lost.

CI runs `python scripts/bump_version.py --check` on every pull request. A tag
whose version does not match the manifests or changelog is rejected before any
desktop build starts.

Release PR workflows explicitly dispatch CI after bot-created or bot-refreshed
branches. This avoids GitHub's suppression of ordinary workflow events created
with the built-in token.

## Local fallback

The same preparation can be run locally:

```bash
# Preview release notes without changing files
python scripts/bump_version.py patch --changelog

# Synchronize files and add the changelog entry
python scripts/bump_version.py patch

# Verify all version sources
python scripts/bump_version.py --check
```

Review the diff and commit only the version files and `CHANGELOG.md`. Do not use
`git add .` in a working tree containing unrelated changes.

To rebuild an existing unpublished tag, open
**Actions → Build and Publish Desktop Release → Run workflow** and enter the
exact tag. The workflow refreshes an existing draft and replaces its assets.
It refuses to overwrite an already published release.

## Repository setup

The workflows use the built-in `GITHUB_TOKEN` for tagging and publication.
No release credential is required.

GitHub suppresses ordinary workflow events caused by its built-in token. The
release pipeline accounts for this by explicitly dispatching the desktop build
after creating the tag.

For repositories that require pull-request checks to be triggered by the
release bot, add a fine-grained `RELEASE_BOT_TOKEN` secret with access to
contents and pull requests. Without it, Release PR creation still works, but
GitHub may not trigger other workflows from the bot-created branch and pull
request. The **Prepare Release** workflow always performs its own version
validation.

Optionally protect the `main` branch and require review of Release PRs. That
keeps changelog approval manual while leaving all mechanical release work
automated.

## Recovery

### A platform build fails

Fix the cause on `main`, prepare a new patch release, and merge it. The failed
version remains a draft and is not advertised as the latest release.

If the failure was transient and the tagged source is correct, rerun
**Build and Publish Desktop Release** with the existing tag.

### A Release PR needs changes

Edit the changelog directly on its `release/vX.Y.Z` branch. Do not rerun
**Prepare Release** for the same version while that branch exists; the workflow
stops instead of overwriting review edits.

### A wrong tag was created

Do not move a published version tag. If the release is still a draft, delete
the draft and tag in GitHub, correct the source through a new pull request, and
then run the desktop workflow for the corrected tag. Prefer issuing a new patch
version once a release has been published.
