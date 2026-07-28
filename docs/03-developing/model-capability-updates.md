# Updating Model Capabilities

Suzent keeps shipped model metadata in `config/capabilities/*.json`. These files
change frequently as providers add models and LiteLLM updates its metadata, so
repository updates are handled by a dedicated GitHub Actions workflow instead
of writing directly to `main`.

## Runtime and repository data

Normal runtime discovery writes to the local user-data overlay:

```text
<SUZENT_DATA_DIR>/capabilities/
```

This keeps ordinary Suzent usage from dirtying the Git working tree. The
tracked files are only updated when `SUZENT_CAPABILITIES_TO_REPO=1` is set.
Developer mode does not set this variable, so provider discovery and sync
continue to use the local overlay while developing.

See [Model Capabilities](../02-concepts/providers/model-capabilities.md) for
details about precedence between shipped data, the local overlay, and global
overrides.

## Automated updates

The **Update Model Capabilities** workflow runs every day at 03:00 UTC and can
also be started manually from the repository's **Actions** tab. It:

1. installs the Python dependencies with `uv`;
2. runs `scripts/sync_model_capabilities.py --to-repo`;
3. commits changes limited to `config/capabilities/*.json`;
4. opens or updates a pull request from
   `automation/model-capabilities`.

The pull-request branch name is fixed. If an update PR is still open, later
runs add new changes to that same PR instead of creating another one. A run
with no capability changes exits without creating a commit. After the PR is
merged, a later run removes the obsolete automation branch; the next model
change starts a new PR.

Because the repository is public and the workflow uses a standard
GitHub-hosted runner, scheduled runs do not consume billable Actions minutes.

## Running the sync locally

Preview a sync in the local overlay:

```bash
uv run python scripts/sync_model_capabilities.py --json
```

Write the generated data to the tracked repository files:

```bash
uv run python scripts/sync_model_capabilities.py --to-repo
```

Review the resulting JSON diff before committing it. To isolate overlay data
during testing, set `SUZENT_DATA_DIR` to a temporary directory.

## Repository setup

The workflow uses the built-in `GITHUB_TOKEN` and declares:

```yaml
permissions:
  contents: write
  pull-requests: write
```

The repository must also allow GitHub Actions to create and approve pull
requests under **Settings > Actions > General > Workflow permissions**.

Pull requests created with the built-in `GITHUB_TOKEN` do not trigger new
`push` or `pull_request` workflow runs. If automated capability PRs must start
the full CI suite, use a fine-grained bot token with repository contents and
pull-request write permissions.
