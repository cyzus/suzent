# Release Guide

Suzent uses a Release PR workflow. Preparing a release is a single manual
action; version synchronization, tagging, cross-platform builds, and GitHub
Release publication are automated.

## Before you start

1. Make sure all changes intended for the release have been merged into
   `main`, and that its required CI checks pass.
2. Decide the next [semantic version](https://semver.org/):
   - `patch` for backward-compatible fixes;
   - `minor` for backward-compatible features;
   - `major` for breaking changes;
   - an exact `X.Y.Z` version only when the automatically calculated version
     is not appropriate.
3. Decide how desktop assets should be handled:
   - use `build` for every normal release and for any frontend, desktop,
     installer, or `API_VERSION` change;
   - use `reuse` only for a backend-only hotfix that remains compatible with
     the previous desktop application.

## Normal release

1. In GitHub, open **Actions → Prepare Release → Run workflow** and select the
   `main` branch.
2. Set **version** to `patch`, `minor`, `major`, or an exact version such as
   `0.8.0`. Set **desktop_assets** to `build` unless the release meets all of
   the `reuse` conditions above, then run the workflow.
3. Wait for the workflow to open a `release/vX.Y.Z` pull request. Do not create
   the release branch, tag, or GitHub Release manually.
4. Review the pull request:
   - confirm the version is correct in every changed manifest and lock file;
   - edit the generated `CHANGELOG.md` section so it is accurate and useful to
     users;
   - confirm `.release-assets-mode` contains the intended `build` or `reuse`
     value;
   - wait for all required checks to pass.
5. Merge the Release PR into `main`. The merge automatically creates the
   `vX.Y.Z` tag and starts **Build and Publish Desktop Release**.
6. Wait for that workflow to complete. The GitHub Release stays in draft state
   until every required asset has been uploaded and checksums are generated.
7. Open the [Releases page](https://github.com/cyzus/suzent/releases) and verify:
   - the release is published rather than draft and is marked as the latest
     release;
   - its title, tag, and release notes match the merged changelog;
   - all eight `suzent-*` application and installer assets are present (two
     each for Windows, Linux, macOS Intel, and macOS Apple Silicon);
   - `SHA256SUMS` is attached.

The release is complete only after the publication and asset checks in step 7
pass. If the workflow fails, follow [Recovery](#recovery) rather than manually
publishing the draft.

The release remains a draft while Windows, macOS Intel, macOS Apple Silicon,
and Linux builds run. It is published only after every build succeeds. A failed
build therefore cannot expose a partially populated release.

Backend-only hotfixes still receive a normal version and Git tag for auditing,
rollback, and dependency locking, but they do not rebuild four desktop targets.
When `desktop_assets=reuse`, the workflow copies the previous published UI and
installer assets into the new release. The frontend accepts a different backend
build commit as long as `API_VERSION` matches. Incompatible route or payload
changes must bump `API_VERSION` and use `desktop_assets=build`.

### If main changes before merge

Do not merge a stale Release PR. Every push to `main` automatically runs
**Refresh Release PR**. It finds the single open same-repository `release/v*`
PR, refreshes it, and starts CI. No PR number or manual action is required.

The refresh workflow merges the latest `main` into the release branch,
regenerates the current version's changelog section, validates every version
source, pushes the result, and explicitly starts CI. Review the regenerated
notes again before merging because refresh replaces any manual edits in that
version's section — with the single exception of the highlights block described
below.

For recovery, **Actions → Refresh Release PR → Run workflow** performs the same
lookup without inputs. If there is no open Release PR it exits successfully. If
there is more than one, it stops and lists the candidates instead of guessing.

The post-merge workflow independently verifies that the Release PR head
contained the latest pre-merge `main` commit. If it did not, tag creation and
publication stop instead of releasing code that is missing from the notes.

### Writing release highlights

A generated changelog section is a flat list of commit subjects. For a large
release that is thirty or more bullets with no indication of what the release is
actually about, and the GitHub release body is this section copied verbatim.

Anything wrapped in highlights markers, placed directly under the version
heading, survives every refresh:

```markdown
## [v0.10.0] - 2026-08-25

<!-- highlights -->
Memory is the story of this release: claims now carry a confirmation count and
an expiry, duplicate facts retire instead of accumulating, and the memory tab
is finally readable.
<!-- /highlights -->

### 🚀 Added
- ...
```

Both markers are required and each must sit alone on its own line. An unclosed
block is discarded on the next refresh rather than swallowing the rest of the
entry. The markers are HTML comments so they stay invisible on the release page.

Write this on the Release PR, before merging, so it goes through review with
everything else and the release is published with its summary already in place.
Drafting it from `git log <last-tag>..HEAD` is a reasonable job to hand to an
agent; deciding which of those commits a user actually cares about is not.

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
uv run python scripts/bump_version.py patch --changelog

# Synchronize files and add the changelog entry
uv run python scripts/bump_version.py patch

# Verify all version sources
uv run python scripts/bump_version.py --check
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
