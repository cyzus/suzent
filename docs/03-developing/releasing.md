# Release guide

Suzent prepares independent release plans for three products:

| Product | Includes | Release PR | What merging does |
| --- | --- | --- | --- |
| `desktop` | Python backend, desktop UI, Tauri app and installer | `release/next` | Records the plan, creates `vX.Y.Z`, and starts the existing desktop build/publication workflow |
| `mobile` | iOS and Android; one shared product version | `release/mobile` | Records the version and changelog; native CI produces test artifacts |
| `browser` | Chrome/Edge extension | `release/browser` | Creates `browser-vX.Y.Z` and publishes the store-ready ZIP; store submission remains manual |

Mobile App Store, Play Store, signed distribution, and GitHub Release publishing
remain future work. A mobile release-plan merge does **not** publish an app or
trigger a desktop release. Browser releases retain their existing reproducible ZIP builder and
`--latest=false` publication, so they never replace the desktop latest release.

## Declare release impact in a feature PR

Add a uniquely named JSON file under `.releases/changes/`, for example
`.releases/changes/secure-local-pairing.json`:

```json
{
  "products": {"desktop": "minor", "mobile": "minor"},
  "summary": "Pair phones with a local desktop over trusted HTTPS without a public domain."
}
```

This is a release decision to review alongside the code, not a conclusion inferred
from a commit title. Each product can have a different impact. Allowed values are
`patch`, `minor`, `major`, and `none`. Unaffected products can be omitted.

For a change to application code that needs no release, explicitly document why:

```json
{
  "products": {"mobile": "none"},
  "summary": "Reorganize internal mobile helpers.",
  "reason": "No shipped behavior or interface changes."
}
```

A PR with only documentation, tests, or CI/tooling changes needs no declaration.
CI requires product coverage for application changes. Shared presentation assets
require a decision for desktop and mobile. Backend changes count as desktop changes;
reviewers must also declare mobile impact if client changes are necessary. Path
checks cannot decide protocol compatibility on their own.

CI validates product names, impact values, summaries, and reasons for `none`.
Before merging, edit the declaration freely. After merging, declarations are
immutable and retained as an audit record; an incorrect *pending version decision*
can be corrected through a release override. Do not delete old declarations.

Conventional Commit titles remain useful development history, but new titles no
longer control product versions. Follow the documented semantic meaning when
choosing impacts. An explicit `major` is deliberate and can take `0.x` to `1.0.0`;
choose `minor` if a pre-1.0 compatibility change should remain pre-1.0.

## What happens after merging

On each push to `main`, **Refresh Release PRs** considers each product separately:

1. Read its current version and consumed-declaration ledger from that exact main
   commit, not from a pending release branch.
2. Collect declarations not yet consumed by that product.
3. Take the highest impact once: three patches mean one patch; a minor plus
   patches means one minor. `none` alone does not open a release PR.
4. Merge main into the product's existing release branch or open one if needed.
5. Update only that product's version files, changelog, and ledger, then run CI.

A declaration affecting multiple products is consumed independently. Shipping mobile
first does not lose the desktop portion. The ledger is recorded atomically with
the release-plan merge, so a refresh cannot open a duplicate release while the
desktop tagging workflow is still starting.

The desktop canonical version remains `src-tauri/tauri.conf.json`, synchronized
across Python, npm, Cargo and installer manifests/locks. The mobile source remains
`packages/mobile-contract/version.json`; release preparation increments its stored
build number once and regenerates iOS/Android version settings. Repeated refreshes
do not keep incrementing it. Native CI retains its separate per-run build-number
allocation for test artifacts; this is not yet a store distribution scheme.

## Review and release

Review the open product Release PR, its version, changelog, and CI results.
Merge using **Create a merge commit** once it contains the latest main. CI verifies
that its versions, consumed declarations and generated notes match its plan and
that no unrelated files were added to the release branch.

For desktop, `.release-assets-mode` remains `build` normally. Use `reuse` only
for a backend-only hotfix compatible with the previous desktop binaries. Any
incompatible API change or changed desktop assets requires `build`.

The desktop GitHub Release stays a draft until every required platform build,
asset upload, and checksum succeeds. Verify the published release, version,
notes, all eight application/installer assets, and `SHA256SUMS`. Do not manually
publish a partially populated draft.

The three product branches may be reviewed and merged independently. When one
merges, refresh the others against main before merging it.

## Browser extension releases

Extension code PRs now add a `browser` declaration instead of changing
`extensions/browser/manifest.json` themselves:

```json
{
  "products": {"browser": "patch"},
  "summary": "Recover the browser connection after the desktop restarts."
}
```

Several browser PRs can accumulate before one release. The `release/browser` PR
updates only the manifest version, browser changelog, and browser ledger. It uses
the same highest-impact calculation and persistent overrides as other products.
Changes to the desktop native host may need a separate `desktop` declaration;
sharing a feature does not couple their version numbers.

Merging an ordinary extension PR no longer publishes anything. Merging the
browser release PR validates the plan against its pre-merge main commit, packages
that exact merged source, tags `browser-vX.Y.Z`, and publishes
`suzent-browser-X.Y.Z.zip`. Browser CI rejects already-used release tags. The ZIP
keeps `manifest.json` at its root and excludes the release-planning metadata.

Upload the ZIP to Chrome and Edge manually as before. To retry an interrupted
GitHub publication, run **Release Browser Extension** with the original merged
release commit or its `browser-v` tag as `release_ref`. Do not use a newer main
commit: reruns validate the original plan and refuse to move a tag to different
source. Existing completed assets are not overwritten.

Browser adoption starts from the current manifest version. Old extension releases
remain unchanged; code PRs merged after adoption use declarations. This does not
re-infer already published browser versions from desktop commit history.

## Persistent version overrides

Do not edit the generated version files directly. On the open product release
branch, record the baseline, desired version, and a reason:

```bash
git fetch origin main
uv run python scripts/release_plan.py override \
  --product desktop --source origin/main --version patch \
  --reason "Reviewed maintenance release"
uv run python scripts/release_plan.py apply --product desktop --source origin/main
```

This writes `.releases/overrides/desktop.json`, for example:

```json
{
  "baseline": "0.14.0",
  "version": "0.14.1",
  "reason": "Reviewed maintenance release"
}
```

Review and commit the override **and** the regenerated product files together.
Subsequent main merges preserve the decision even if new declarations arrive.
Reviewers remain responsible for whether the override is still appropriate for
the accumulated changes. The reason remains in Git history. After the target
version has shipped, the override is spent and does not pin later releases.
Remove an active override to return to automatic calculation, then apply again.

If there is no open product Release PR, use **Actions → Prepare Release**. Choose
`desktop`, `mobile`, or `browser`, then `auto`, a bump type, or an exact version. An explicit
version requires a reason and is stored as the same persistent override. An
existing open PR is never replaced; edit it instead. Preparation and refresh use
the same concurrency lock.

## Release notes and highlights

Product summaries come from declarations. Desktop notes also include any pending
legacy commits during migration. Editorial highlights survive refreshes when
placed immediately below the pending release heading:

```markdown
<!-- highlights -->
This release makes local mobile pairing easier to set up.
<!-- /highlights -->
```

Keep both markers on separate lines. Other generated pending notes are rebuilt;
previously published entries are preserved. Desktop notes live in `CHANGELOG.md`,
mobile notes in `packages/mobile-contract/CHANGELOG.md`, and browser notes in
`.releases/changelogs/browser.md` (outside the packaged extension directory).

## Migration from commit-based versions

The first-parent commit introducing `.releases/config.json` is the adoption
boundary. Until the first desktop release under this policy, commits before that
boundary and after the last reachable desktop release tag use the old rules:
`feat` → minor, `fix`/`perf` → patch; breaking changes → major, or minor below 1.0.
This includes old PRs merged while the policy PR was being reviewed.

New declarations and pending legacy impact are combined, taking the highest.
After the desktop ledger records the migration as consumed, old history is never
counted again. Mobile starts from its existing explicit version with declarations;
old mobile changes were already handled by the legacy whole-app policy and are
not inferred a second time.

Existing feature PRs merged after adoption must add declarations before merging.
The rolling desktop branch remains `release/next`, so an existing Release PR can
be migrated by the next refresh. If its generated version files conflict, refresh
resolves those files from main and regenerates them; genuine conflicts elsewhere
stop for manual resolution. Legacy versioned `release/*` branches must be closed
or moved to `release/next` before enabling the new workflow.

## Local validation

```bash
uv run python scripts/release_plan.py check --base origin/main
uv run python scripts/release_plan.py plan --product desktop --source HEAD
uv run python scripts/release_plan.py plan --product mobile --source HEAD
uv run python scripts/release_plan.py plan --product browser --source HEAD
uv run python scripts/bump_version.py --check
uv run python scripts/generate_mobile_version.py --check
```

`plan` reads committed declarations at the selected source. `apply` is for a
release branch and must use the main baseline, normally `--source origin/main`.
It never publishes, tags, or pushes. `bump_version.py` remains the desktop
synchronization library and validator; its old mutating release CLI is disabled
after policy adoption to prevent bypassing the release ledger.

## Permissions and recovery

`RELEASE_BOT_TOKEN` is optional with a fallback to `GITHUB_TOKEN`; it needs
repository Contents, Pull requests, and Workflows write access. Explicit workflow
dispatch uses the built-in token with Actions write permission. The workflows explicitly start CI so checks do not
depend on events emitted by the built-in token. Require the **Release plan** check
in branch protection alongside application checks.

A failed refresh stops without discarding reviewed overrides or unrelated
conflicts. Fix the conflict, then rerun **Refresh Release PRs**. A stale release PR
fails validation until refreshed. A failed desktop build leaves a draft; retry
transient failures at the same tag, or fix source through a new patch release.
Never move a published tag or overwrite published assets.
