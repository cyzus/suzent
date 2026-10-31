# AGENTS.md

## Project Overview

Suzent is a personal AI agent — Python backend (FastAPI + pydantic-ai) with a React/TypeScript + Tauri desktop frontend.

## Documentation

Full documentation lives in `docs/`. Each numbered folder is a sidebar section on the site:
- `01-getting-started/` — what Suzent is, quickstart, platforms, updating
- `02-using/` — how to work with the agent: tasks, projects, and setting it up
- `03-features/` — memory, tools, skills, workspace, automation, devices, GitHub sync
- `04-models/` — one page per provider, grouped into `cloud/` and `local/`, plus model roles
- `05-chat-apps/` — one page per chat app, plus access control
- `06-tutorials/` — task-oriented walkthroughs
- `07-reference/` — CLI, slash commands, settings pages, configuration, FAQ and troubleshooting
- `08-developing/` — contributor docs, grouped into `contributing/`, `architecture/` (how it works today), and `protocols/`; planned work and known gaps go in `roadmap.md`, not in those pages

`docs/` powers the user-facing site at suzent.com/docs. Keep `01` to `07` written for users (settings, steps, plain language; no class names, REST tables, or code internals) and put implementation detail in `08-developing/`.

## General Principles

- Follow OOP principles and write idiomatic, Pythonic code
- Use type hints everywhere in Python
- Keep functions focused on a single responsibility
- No unnecessary abstractions: three similar lines beat a premature helper

## Package Management

- Use `uv` for all Python dependency management (`uv sync`, `uv add`, `uv run`)
- Frontend: use `npm` inside `frontend/` or `src-tauri/`

## Python Backend (`src/suzent/`)

- Python 3.12+; use modern syntax (`match`, `TypeAlias`, `type X = ...`)
- Async-first: prefer `async def` for I/O-bound operations
- Use `loguru` logger — follow log levels in `CONTRIBUTING.md`:
  - `DEBUG`: diagnostics, state transitions
  - `INFO`: lifecycle events, successful operations
  - `WARNING`: recoverable failures, fallbacks
  - `ERROR`: unrecoverable failures with `traceback.format_exc()`
- Never log secrets, credentials, or PII
- Use `pydantic` models for data validation at system boundaries
- Use `from suzent.logger import get_logger` then `logger = get_logger(__name__)` — never `from loguru import logger` directly. `get_logger` binds the module name that the configured log format renders; it returns the one centralized loguru logger rather than creating a new one

## Frontend (`frontend/src/`)

- React functional components with hooks only — no class components
- TypeScript strict mode; always type props and return values
- Follow existing component patterns in `frontend/src/components/`
- Use `i18n` for all user-visible strings
- Return early on `isImeComposing(e)` (`frontend/src/lib/ime.ts`) in any key handler that can fire while typing text, including document/window listeners: on macOS the Enter that confirms an IME candidate otherwise sends or submits

## Testing (`tests/`)

- Write `pytest` unit tests for new functionality
- Use `pytest-asyncio` for async tests (`asyncio_mode = "auto"`)
- Mark appropriately: `@pytest.mark.sandbox` (requires Docker), `@pytest.mark.integration` (external services), `@pytest.mark.slow`
- Run: `uv run pytest` or `uv run pytest -m "not sandbox"` to skip Docker tests

## Release Declarations (required before opening a PR)

CI's **Release plan** check fails any PR that changes shipped code without a release declaration. Before you push a PR, check whether you need one:

- Needed when the PR touches `src/`, `frontend/`, `src-tauri/`, `apps/`, `extensions/browser/`, `packages/`, `pyproject.toml` or `uv.lock`
- Not needed for PRs that only change docs, tests, CI or tooling
- Add a new file `.releases/changes/<short-kebab-slug>.json` in the same PR:
  ```json
  {"products": {"desktop": "patch"}, "summary": "One user-facing sentence, used in the release notes."}
  ```
- Products: `desktop` (includes the backend), `mobile`, `browser`. Impact: `patch`, `minor`, `major`, or `none` with a `"reason"`
- Never edit or delete an existing declaration, and never change product versions in a feature PR
- Verify locally: `git fetch origin main && python scripts/release_plan.py check --base origin/main`

Details: `.releases/README.md` and `docs/08-developing/contributing/releasing.md`.

## Code Style

- Run `pre-commit run --all-files` before committing
- Linter: `ruff` (configured in `pyproject.toml`)
- No commented-out code; no TODOs without a linked issue
- Comments only when the *why* is non-obvious — never explain what the code does

## Architecture Notes

- Agent logic lives in `src/suzent/core/` and `src/suzent/nodes/`
- Tools are registered in `src/suzent/tools/`
- Channel integrations (Telegram, Slack, Discord) live in `src/suzent/channels/`
- Memory system uses LanceDB (`src/suzent/memory/`)
- Sandbox execution uses Docker (`src/suzent/sandbox/`)
- Skills are in `skills/` at the repo root
