# Release Guide

Suzent keeps a Release PR permanently open against `main`. There is no "start a
release" step: every push to `main` re-merges into that PR, re-derives the
version from the commit range, and rewrites the notes. Releasing is a merge.

Version synchronization, tagging, cross-platform builds, and GitHub Release
publication are automated from there.

## Before you start

1. Make sure everything intended for the release is merged into `main` and its
   CI checks pass.
2. Check that the derived version on the open Release PR is the one you want.
   You do not choose it — it comes from the commit prefixes in the range since
   the last tag:

   | Prefix in the range | Bump |
   | --- | --- |
   | `feat:` | minor |
   | `fix:`, `perf:` | patch |
   | `feat!:`, or a `BREAKING CHANGE:` footer | major, but **minor while below 1.0** |
   | only `chore:`, `ci:`, `docs:`, `test:`, `style:`, `build:`, `refactor:` | patch, as maintenance |

   The highest-ranking prefix in the range wins, so one `feat:` among twenty
   fixes makes the release a minor. Reaching 1.0.0 stays a deliberate human act:
   a breaking change below 1.0 bumps the minor rather than declaring stability.
3. Check `.release-assets-mode` on the release branch:
   - `build` for every normal release and for any frontend, desktop, installer,
     or `API_VERSION` change;
   - `reuse` only for a backend-only hotfix that remains compatible with the
     previously published desktop application.

   It carries over from `main`, so it is `build` unless someone changed it.

## Normal release

1. Open the Release PR — it is the open pull request from `release/next`,
   titled `chore: release vX.Y.Z`. If none is open, nothing user-visible has
   landed since the last tag; see [Nothing is open](#nothing-is-open).
2. Review it:
   - confirm the derived version is what you intend, in the title and in every
     changed manifest and lock file;
   - read the generated `CHANGELOG.md` section, and add a
     [highlights block](#writing-release-highlights) so the release page opens
     with something better than a list of commit subjects;
   - confirm `.release-assets-mode` holds the intended `build` or `reuse`;
   - wait for all checks to pass.
3. Merge it into `main` with **Create a merge commit**. The branch is `main`
   plus a version bump, so squashing writes a redundant duplicate-content
   commit. The merge automatically creates the `vX.Y.Z` tag and starts
   **Build and Publish Desktop Release**.
4. Wait for that workflow to complete. The GitHub Release stays a draft until
   every asset is uploaded and checksums are generated.
5. Open the [Releases page](https://github.com/cyzus/suzent/releases) and verify:
   - the release is published rather than draft, and is marked as latest;
   - its title, tag, and notes match the merged changelog;
   - all eight `suzent-*` application and installer assets are present (two
     each for Windows, Linux, macOS Intel, and macOS Apple Silicon);
   - `SHA256SUMS` is attached.

The release is complete only after the checks in step 5 pass. If the workflow
fails, follow [Recovery](#recovery) rather than publishing the draft by hand.

The release remains a draft while the Windows, macOS Intel, macOS Apple
Silicon, and Linux builds run, and is published only after every build
succeeds — so a failed build cannot expose a partially populated release.

Backend-only hotfixes still receive a normal version and Git tag for auditing,
rollback, and dependency locking, but they do not rebuild four desktop targets.
With `.release-assets-mode` set to `reuse`, the workflow copies the previously
published UI and installer assets into the new release. The frontend accepts a
different backend build commit as long as `API_VERSION` matches. Incompatible
route or payload changes must bump `API_VERSION` and use `build`.

Do not create the release branch, tag, or GitHub Release by hand.

### Nothing is open

A range containing only `chore`, `ci`, `docs`, `test`, `style`, `build`, or
`refactor` commits does not open a Release PR on its own. Nothing in it earns a
bump, so there is nothing a user would notice; it waits and rides along with the
next real change.

To release anyway — to ship a dependency bump, say — use
[Prepare Release](#manual-override-prepare-release).

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

### Releasing a version other than the derived one

Edit the version files on `release/next` before merging. The tag follows the
files at merge time, not the branch name — which is why the branch is called
`release/next` and never names a version.

Be aware that the next push to `main` re-derives the version and will overwrite
a hand-edited one. Only the highlights block survives a refresh.

### If main changes before merge

Do not merge a stale Release PR — though you rarely have to think about it,
because every push to `main` runs **Refresh Release PR** automatically. It finds
the single open same-repository PR whose head branch starts with `release/`,
merges `main` into it, re-derives the version, rewrites the notes, validates
every version source, pushes, and starts CI. No PR number or manual action is
required.

The refresh replaces any manual edits in the pending version's changelog
section, with the single exception of the highlights block above. If the branch
is already up to date with `main`, or the reconcile produces no file changes, it
makes no commit at all.

For recovery, **Actions → Refresh Release PR → Run workflow** performs the same
lookup without inputs. If there is no open Release PR it exits successfully. If
there is more than one, it stops and lists the candidates instead of guessing.

The post-merge workflow independently verifies that the Release PR head
contained the latest pre-merge `main` commit. If it did not, tag creation and
publication stop instead of releasing code that is missing from the notes.

## What is automated

`scripts/bump_version.py` synchronizes the version in:

- the Python project and `uv.lock`;
- the frontend and desktop npm manifests and lock files;
- the main Tauri configuration, Cargo manifest, and Cargo lock;
- the standalone installer's Tauri, npm, and Cargo files.

It also generates the changelog section from commits since the last tag. Scoped
conventional commits such as `feat(ui): ...` are categorized, while unprefixed
subjects are retained under **Changed** so release notes are not silently lost.
The baseline for re-deriving the version is always the last *tagged* release,
never the version already written into the release branch — otherwise each push
would bump on top of the previous bump.

CI runs `python scripts/bump_version.py --check` on every pull request, and
advisory-audits commit prefixes it cannot read. A prefix nobody recognizes earns
no bump, so an unreadable one silently changes the version that ships; the audit
warns without blocking a merge. A tag whose version does not match the manifests
or changelog is rejected before any desktop build starts.

Release workflows explicitly dispatch CI and the desktop build rather than
relying on the push events they create. GitHub suppresses ordinary workflow
events triggered by its built-in token, and this is what works around it.

## Manual override: Prepare Release

**Actions → Prepare Release → Run workflow** opens a release branch with a
version you choose. Use it only when the automatic flow will not do:

- to ship a range the automatic flow considers unreleasable;
- to force an exact version, a major, or a bump the prefixes do not imply;
- to set `.release-assets-mode` to `reuse` as the branch is created.

Set **version** to `auto`, `patch`, `minor`, `major`, or an exact version such
as `0.8.0`, and **desktop_assets** to `build` or `reuse`.

It refuses to run while `release/next` already exists, rather than overwriting
review edits on an open PR. Close that PR and delete the branch first, or just
edit the version files on the branch that is already open.

## Local fallback

The same preparation can be run locally:

```bash
# Preview release notes without changing files
uv run python scripts/bump_version.py patch --changelog

# Show the bump the commit history implies, without changing files
uv run python scripts/bump_version.py --suggest-bump

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

Tagging and publication use the built-in `GITHUB_TOKEN`.

Opening and refreshing the Release PR uses `RELEASE_BOT_TOKEN`, a fine-grained
personal access token scoped to this repository, falling back to `GITHUB_TOKEN`
when the secret is absent. Without it the Release PR is still created and
refreshed, but GitHub will not run `pull_request` workflows on a branch the
built-in token pushed, so the PR's checks never start.

The token needs **Contents: Read and write**, **Pull requests: Read and write**,
and **Workflows: Read and write**. The last one is not optional: the refresh
merges `main` into the release branch, and that merge carries any change under
`.github/workflows/`, which GitHub refuses from a token without it.

Optionally protect the `main` branch and require review of Release PRs. That
keeps changelog approval manual while leaving all mechanical release work
automated.

## Recovery

### A platform build fails

Fix the cause on `main`, let the refreshed Release PR pick up the fix, and merge
it. The failed version remains a draft and is not advertised as the latest
release.

If the failure was transient and the tagged source is correct, rerun
**Build and Publish Desktop Release** with the existing tag.

### A Release PR needs changes

Edit the changelog or the version files directly on `release/next`. Do not rerun
**Prepare Release** for the same version while that branch exists; the workflow
stops instead of overwriting review edits.

Remember that the next push to `main` regenerates the changelog section. Put
anything you want to keep inside the highlights markers.

### More than one Release PR is open

**Refresh Release PR** stops and lists the candidates rather than guessing which
one to update. Close the ones that are not wanted, delete their branches, and
re-run the workflow.

### A wrong tag was created

Do not move a published version tag. If the release is still a draft, delete
the draft and tag in GitHub, correct the source through a new pull request, and
then run the desktop workflow for the corrected tag. Prefer issuing a new patch
version once a release has been published.
