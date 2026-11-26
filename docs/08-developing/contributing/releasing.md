---
sidebar_position: 4
---

# Release guide

Suzent prepares independent release plans for three products:

| Product | Includes | Release PR | What merging does |
| --- | --- | --- | --- |
| `desktop` | Python backend, desktop UI, Tauri app and installer | `release/next` | Records the plan, creates `vX.Y.Z`, and starts the existing desktop build/publication workflow |
| `mobile` | iOS and Android; one shared product version | `release/mobile` | Creates `mobile-vX.Y.Z`, publishes signed Android assets, rolls Android out on Google Play, and submits iOS to App Review, released automatically on approval |
| `browser` | Chrome/Edge extension | `release/browser` | Creates `browser-vX.Y.Z` and publishes the store-ready ZIP; store submission remains manual |

Mobile signing requires the `mobile-release` environment. See
[Mobile release distribution](mobile-releases.md) for credentials, recovery, and
acceptance requirements. Browser store submission remains manual.
Mobile and browser releases use `--latest=false`, so they never replace the
desktop latest release.

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
Dependabot PRs that only touch dependency manifests and lockfiles need none either;
the bump ships with the next declared release.
CI requires product coverage for application changes. Shared presentation assets
require a decision for desktop and mobile. Backend changes count as desktop changes;
reviewers must also declare mobile impact if client changes are necessary. Path
checks cannot decide protocol compatibility on their own.

CI validates product names, impact values, summaries, and reasons for `none`.
Before merging, edit the declaration freely. After merging, declarations are
immutable and retained as an audit record; an incorrect *pending version decision*
can be corrected through a release override. Do not delete old declarations.

Conventional Commit titles remain useful development history, but new titles no
longer control product versions.

## Choosing the impact

The impact is not a judgement of how much work went into the PR, how many files it
touched, or how proud you are of it. It is a claim about **what changes for someone
who already uses Suzent**. Ask one question and answer it honestly:

> After this ships, can a user point at something and say "I could not do this before"?

That single test separates `minor` from `patch`, and it is the one that goes wrong
most often.

### The one-line test

Write the release note sentence for your change.

- "Now you can **[a thing that was previously impossible]**." → **`minor`**
- "**[An existing thing]** is now faster / clearer / more reliable." → **`patch`**

If the only honest sentence is "this thing that already worked is now nicer to
use", it is a patch. A refactor that happens to be visible on screen is still a
patch if the screen already did that before.

### The levels

| Impact | Means | Typical triggers |
| --- | --- | --- |
| `major` | Users must act to keep working: stored data, configuration, or a published protocol changes incompatibly. | Chat storage format change, plugin API break, settings migration users must complete by hand |
| `minor` | A **new surface, capability, channel, integration, or user-visible mode** that did not exist before. | A new tool or panel, a new place to have a conversation, a new mail/system integration, a new way to control the app |
| `patch` | An existing capability gets faster, clearer, more reliable, better looking, or gets a real bug fixed. | Search added to an existing picker, animation parity across platforms, faster file opening, a misrendered element fixed |
| `none` | Nothing a user can observe changes. | Internal refactor, dev-server or build config, tests, test-affecting only |

### Worked examples

These come from real PRs in this repository and show where the line sits.

`minor`

- A Mailbox that collects webhooks, scheduled runs and agent messages in one inbox
  with learned routing. Nothing like it existed.
- A side panel that lets you follow the chat Regent handed work to without leaving
  Regent. A new way to work in the app.
- Signing in to Gmail or Outlook through the browser instead of hand-entering IMAP
  settings. A new connection path.

`patch`

- Adding search, collapsible groups and starred favourites to the model selector.
  **Every model was already selectable** once enabled in Settings; this makes
  choosing one faster. The list of things you can do with Suzent is unchanged.
- Moving a bot animation into a shared package so iOS, Android and desktop play the
  same one. The phone already showed a bot; it now shows the desktop's bot. Real
  engineering, patch impact.
- Delivering cross-chat agent messages in parallel instead of one at a time. The
  messages already arrived; they arrive sooner.
- Bumping a dependency, or prebundling packages for the Vite dev server.
  `none`, or a patch if user-visible.

### Judgement calls worth stating

- **A new setting for existing behaviour is usually `patch`.** A toggle that turns
  something already-possible on or off does not reveal a new capability. If the
  setting unlocks something genuinely new, it is the unlock that decides, and that
  unlock usually has its own declaration.
- **`refactor` is not an impact level.** A refactor with no visible change is
  `none`; one that also changes behaviour takes the impact of that behaviour.
- **Cross-platform parity work is `patch` when the other platform already had it.**
  Catching one client up to another does not add a capability to the product; it
  evens it out.
- **Performance is `patch` unless it enables something previously unusable.** Ten
  times faster on an operation nobody could complete is a capability; twice as fast
  on one everybody used is a patch.
- **One PR, one impact.** Do not inflate to `minor` because the body is long. If a
  PR genuinely contains an independent new capability, consider splitting it so the
  release history stays readable.

### When in doubt, go one level lower

A `patch` that should have been `minor` costs a version number and is corrected in
the next release. A `minor` that should have been `patch` publishes a version bump
that promises users something new and delivers a nicety, and once published it
cannot be undone. Under-claim and let several patches ride together; a release does
not need to be large to be frequent.

Reviewers should treat the impact value as part of the code review, not as
bookkeeping. If the summary and the impact disagree, that is a review comment.

### Correcting a merged mistake

Declarations are immutable once merged. If a pending release is over-levelled,
correct the *pending version decision* with an override rather than editing the
declaration:

```bash
git fetch origin main
uv run python scripts/release_plan.py override \
  --product desktop --source origin/main --version patch \
  --reason "Model picker is a usability refinement of an existing selector, not a new capability"
uv run python scripts/release_plan.py apply --product desktop --source origin/main
```

See [Persistent version overrides](#persistent-version-overrides) for the full rules.

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
Merge using **Squash and merge** once it contains the latest main. CI verifies
that its versions, consumed declarations and generated notes match its plan and
that no unrelated files were added to the release branch.

For desktop, `.release-assets-mode` remains `build` normally. Use `reuse` only
for a backend-only hotfix compatible with the previous desktop binaries. Any
incompatible API change or changed desktop assets requires `build`.

The desktop GitHub Release stays a draft until every required platform build,
asset upload, and checksum succeeds. Verify the published release, version,
notes, all eight application/installer assets, the `suzent-webui.zip` web UI
bundle (rebuilt from the tag in both asset modes), and `SHA256SUMS`. Do not manually
publish a partially populated draft.

Every desktop release also builds the Electron app's standard installers
(`desktop-installers.yml`, called with the tag): `Suzent-Setup-<version>-win-x64.exe`
(what Windows users download) and the `Suzent-<version>-win-x64.exe` package it
carries (what electron-updater installs),
`-mac-arm64.dmg`/`.zip`, `-linux-x86_64.AppImage` and
`-linux-amd64.deb`, with their blockmaps and the electron-updater feeds
`latest.yml`, `latest-mac.yml` (written per Mac architecture and joined by
`scripts/merge_mac_update_feed.py`) and `latest-linux.yml`. Each installer is
installed and started on its runner before it is attached, and `SHA256SUMS`
covers them.

Git-checkout installs keep updating through Git until a release carries an
`installer-migration.json` asset. When it does, the updater moves them to the
standard installer instead: it downloads and checks that platform's installer,
stops the old install, removes its shortcuts and `suzent` command, installs the
app and moves the background service onto it; `~/.suzent` is shared, so data
carries over. Attach the marker only after testing the installers on real
machines:

```bash
echo '{}' > installer-migration.json
gh release upload vX.Y.Z installer-migration.json
```

Removing the asset stops further moves. Each move is recorded in the old
checkout's `.suzent/migrated-to-installer.json`.

Once the release is published, the `publish-npm` job copies its files into four
npm packages, `@suzent/desktop-win32-x64`, `desktop-darwin-arm64`,
`desktop-darwin-x64` and `desktop-linux-x64`, each holding that platform's app
and installer plus the web UI bundle and `SHA256SUMS`. npmmirror copies every
npm package without review, so on a mainland China network the installer,
updater, setup scripts and `suzent update` download these packages from
`registry.npmmirror.com` first and fall back to GitHub. The job publishes with
npm Trusted Publishing, so no npm token is stored, and its failure never affects
the GitHub release.
To publish an already published release to npm by itself, run the **Build and
Publish Desktop Release** workflow by hand with its tag and **npm_only** checked.

Trusted Publishing can only be configured on a package that already exists, so
the packages were created once by hand:

```bash
npm login
python scripts/pack_npm_release.py --bootstrap --publish npm-bootstrap
```

This publishes an empty `0.0.0` of each package, which every client ignores.
Then, on npmjs.com, open each package's **Settings → Trusted Publisher**, choose
GitHub Actions, and enter owner `cyzus`, repository `suzent` and workflow
`build-desktop.yml`, leaving the environment empty.

The three product branches may be reviewed and merged independently. When one
merges, refresh the others against main before merging it.

### Plugin programs on npm

Programs that plugins download (see `binaries` in
[the plugin architecture](../architecture/plugins.md#binaries)) also come from
npm, so the same mirror covers them. When an upstream project publishes no npm
package of its own, Suzent republishes its release unchanged under `@suzent`:

- **himalaya** (the email plugin's CLI, MIT OR Apache-2.0):
  `scripts/pack_himalaya_npm.py` pins the version and the SHA-256 of each
  GitHub release archive, takes only the `himalaya` binary and the license
  files out of it, and writes `@suzent/himalaya-<platform>`. The
  **Publish himalaya npm packages** workflow (`publish-himalaya.yml`) runs
  when that file changes on main, or by hand. It skips versions already on
  npm and writes the SHA-256 of each tarball it publishes to the run summary; that is
  the hash to pin in the plugin's `plugin.yaml`.

To update himalaya, change `VERSION`, `ARCHIVES` and `LICENSES` in the script
from the new release's asset digests, and merge.

Like the desktop packages, each new package name has to be published once by
hand before Trusted Publishing can be set up for it, with workflow
`publish-himalaya.yml` as the trusted publisher:

```bash
npm login
python scripts/pack_himalaya_npm.py --bootstrap --publish npm-bootstrap
```

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
