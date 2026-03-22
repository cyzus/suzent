# Suzent Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.4.1]

### 🚀 Added
- **Slash Command System**: Introduce slash command system registered to desktop app and telegram.
- **Canvas (A2UI)**: Agents can render interactive UI surfaces in the sidebar canvas panel or inline in chat using the `render_ui` tool.
  - Component types: `card`, `stack`, `columns`, `text`, `badge`, `button`, `table`, `form`, `list`, `progress`, `divider`.
  - Canvas tab auto-opens when a surface is rendered; supports multiple named surfaces with a tab strip.
  - Button clicks and form submits are sent back to the agent as structured messages, enabling interactive workflows.
  - Surfaces persist across the session; re-rendering with the same `surface_id` upserts in place.
  - Fullscreen mode, drag-to-resize sidebar, and markdown rendering in text/list/table cells.
  - New `canvas` skill (`skill_execute("canvas")`) provides the agent with full component reference and examples.
- **`ask_question` tool**: Dedicated tool for collecting user input that blocks the agent until the user responds, then returns answers as structured data.
  - Single question with options renders as an inline button list; multiple questions or multi-select render as a paged form (one question per page).
  - Paged form includes Back / Skip / Next navigation; Next is only enabled once the current field has a value.
  - `allow_free_text` adds a "Type something else…" option inline as the last list item.
  - **Form field types**: `select` and `multiselect` fields render as inline option lists instead of dropdowns — no portal positioning issues inside inline surfaces.
  - **Paged form mode**: Forms support `paged: true` to show one question at a time with progress indicator.

### ⚡ Changed
- **Context Compact System**: Optimize the context compressor. It can be triggered manually or when the estimated tokens beyond a threshold.
- **Sandbox Docker**: Use Docker as the default sandbox.


## [v0.4.0]

### 🚀 Added
- **Tool Approval (HITL)**: Sensitive tools now pause and ask for user confirmation before running.
  - Desktop app shows an inline approval dialog during streaming.
  - CLI prints a boxed prompt with `suzent agent approve <id>` / `deny <id>` commands.
  - Social channels receive an alert message; reply `/y` or `/n` to respond.
  - Automated contexts (cron, heartbeat) auto-approve by default.
  - Session-level "remember" option to skip repeated prompts for the same tool.
- **Image Generation**: New tool for generating images via the configured provider.
- **Social Slash Commands**: `/help`, `/y`, `/n` command framework for social channels.
- **Agent Steering**: user can send additional text while the agent is actively streaming to redirect its behavior. 
- **Dark Mode**: Add dark mode to the desktop app.
- **Provider Abstraction**: Add provider abstraction layer for easy provider management.

### ⚡ Changed
- **Pydantic AI Migration**: Agent runtime moved from Smolagents to pydantic-ai, bringing native async streaming, structured tool definitions, and deferred-tool support for HITL.
- **Stream Parser**: Unified SSE parser (`StreamParser`) shared across CLI, social, and internal consumers — replaces per-module parsing logic.
- **Approval Manager**: Centralized `approval_manager` module replaces per-stream approval state, enabling cross-interface resolution (e.g. approve from CLI while streaming in desktop).
- **Heartbeat**: Heartbeat can be enabled per session.

### 🐛 Fixed
- **Image Input**: Fixed image input error.
- **Memory loss when stopped by user**: Fixed memory loss caused by stop.

## [v0.3.0]

### 🚀 Added
- **Automation**: Two independent automation systems for proactive agent execution.
  - **Cron Jobs**: Schedule prompts to run on a cron expression in isolated sessions (`cron-{id}`).
    - Full CRUD via Settings > Automation UI, CLI (`suzent cron`), and REST API.
    - Delivery modes: `announce` (status bar notification) or `none` (silent).
    - Per-job model override; falls back to user preference.
    - Exponential backoff retry with auto-deactivation after 5 consecutive failures.
    - Run history stored in `cron_runs` table — viewable per-job in UI and via `suzent cron history`.
    - Inline edit form in the job list card.
  - **Heartbeat**: Periodic ambient monitoring in a persistent `heartbeat-main` chat.
    - Reads `/shared/HEARTBEAT.md` checklist on each tick (configurable and default 30-minute interval).
    - `HEARTBEAT_OK` sentinel suppresses notifications when nothing needs attention.
    - Checklist editable directly in Settings > Automation or by the agent via file tools.
    - Enable/disable toggle and "Run Now" button in UI; `suzent heartbeat` CLI subcommand group.
- **CLI**: New subcommand groups for automation.
  - `suzent cron list|add|edit|remove|toggle|trigger|history|status`
  - `suzent heartbeat status|enable|disable|run`
- **Skills**: New `automation` skill documenting both systems for agent-driven scheduling.
- **Database**: `cron_jobs` table for job configuration; `cron_runs` table for execution history.
- **Docs**: [Automation guide](docs/02-concepts/automation/automation.md) covering cron expressions, heartbeat format, CLI reference, API reference, architecture, and troubleshooting.
- **i18n**: Support zh-CN in desktop app

### ⚡ Changed
- **Memory**: Cron and heartbeat now run with memory fully enabled — agent can read and write long-term memory during scheduled tasks.
- **Subprocess**: `BashTool` now uses `errors="replace"` when decoding subprocess output, preventing crashes on non-UTF-8 output (e.g. GBK on Chinese Windows).
- **Frontend**: Update the streaming and intermediate step output visuals.

### 🐛 Fixed
- **Database**: Added migration to drop legacy `is_heartbeat` column from `cron_jobs` table.


## [v0.2.8]

### 🐛 Fixed
- **Desktop App**: Fix MacOS window hanging whilst waiting for backend startup
- **Desktop App**: Fix Environment Path for desktop app
- **CLI**: Fixed recursive execution hang by nullifying stdin for backend subprocesses.
- **CLI**: Fixed connectivity issues by correctly handling dynamic port allocation in nested environments.
- **CLI**: Fixed `AuthenticationError` in CLI tools (like `speak`) by loading API keys from the database into the CLI environment.
- **Backend Setup**: Added lock check during backend environment setup to prevent `uv venv` from corrupting the virtual environment if the CLI attempts an upgrade while the GUI server is running.
- **CLI/Backend**: Fixed an issue where new configuration keys (like `TTS_MODEL` for Gemini support) were not being deployed to existing users. The backend now consistently deploys example fallback configurations so they can be seamlessly queried by tools like `suzent agent speak`.
- **Installer/Startup**: Fixed an issue where the application would hang in the "Initializing" state when auto-launched by the NSIS installer or from the Start Menu on a fresh install. The application now properly sanitizes its working directory and standard I/O streams for setup subprocesses.

## [v0.2.7]

### 🚀 Added
- **Social Messaging Tool**:
  - Now suzent could proactively send messages to any configured social platform.
- **Voice**:
  - Add voice support for suzent.
- **Node System**: OpenClaw-inspired node architecture for controlling companion devices (phones, desktops, headless servers) remotely.
  - `NodeBase` ABC and `NodeManager` for device registry, lookup, and command dispatch.
  - `WebSocketNode` with JSON-RPC-style invoke/result protocol and heartbeat support.
  - WebSocket endpoint (`/ws/node`) for node connections with Pydantic-validated handshake.
  - REST endpoints for listing (`/nodes`), describing (`/nodes/{id}`), and invoking commands (`/nodes/{id}/invoke`).
  - Pydantic models for all protocol messages and API schemas (`nodes/models.py`).
  - `nodes_enabled` and `node_auth_mode` configuration fields.
- **CLI Overhaul**: New subcommand groups alongside existing commands.
  - `suzent nodes list|status|describe|invoke` — manage connected nodes.
  - `suzent agent chat|status` — interact with the agent from the terminal.
  - `suzent config show|get|set` — view and modify configuration.
- **Skills**: New `nodes` skill teaching the agent to use `suzent nodes` commands via `BashTool`.


## [v0.2.6]

### 🚀 Added
- **Memory**:
  - Markdown memory layer — human-readable source of truth in `/shared/memory/` with daily logs (`YYYY-MM-DD.md`) and curated `MEMORY.md`.
  - Dual-write architecture — every extracted fact persisted to both markdown and LanceDB.
  - `MarkdownIndexer` for rebuilding LanceDB from markdown source of truth.
  - `TranscriptIndexer` for chunking and embedding JSONL transcripts into LanceDB (opt-in via `transcript_indexing_enabled`).
  - Transcript-linked facts with `source_session_id`, `source_transcript_line`, `source_timestamp` fields.
- **Session**:
  - JSONL per-session transcripts at `.suzent/transcripts/{session_id}.jsonl`.
  - Session lifecycle management with daily reset, idle timeout, and max turns policies.
  - `StateMirror` writes inspectable JSON snapshots to `.suzent/state/{session_id}.json`.
- **Agent State**: JSON v2 serialization format replacing opaque pickle, with backward-compatible deserialization.
- **Context**: Pre-compaction memory flush — extracts facts from steps before context compression discards them.
- **API**: New endpoints: `/session/{id}/transcript`, `/session/{id}/state`, `/memory/daily`, `/memory/daily/{date}`, `/memory/file`, `/memory/reindex`.
- **Frontend**:
  - Memory view sub-navigation with Overview, Daily Logs, MEMORY.md, and Transcripts tabs.
  - DailyLogsPanel, MemoryFilePanel, and TranscriptPanel components.
  - Extended memoryApi with 6 new API client functions and TypeScript types.

### ⚡ Changed
- **Memory**: 
  - Fact extraction prompts rewritten for concise one-sentence-per-fact output.
  - Retrieved memories formatted as single-line entries.
- **Context**: `ContextCompressor` now accepts `chat_id`/`user_id` for pre-compaction flush.
- **Database**: `ChatModel` extended with `last_active_at` and `turn_count` fields (nullable migration).
- **Frontend**: improve thinking animation.

## [v0.2.5]
### ⚡ Changed
- **Desktop Build**: Replace PyInstaller/Nuitka compilation with bundled Python + uv architecture
  - Bundle standalone Python 3.12 distribution and uv package manager
  - First-run venv creation via uv (~10-30s on first launch)
  - All native dependencies (Playwright, lancedb, crawl4ai) now work natively
  - Build time reduced from minutes/hours to ~30 seconds
- **Playwright**: Auto-install Chromium browser on first launch (no manual setup needed)
- **File Viewer**: Fix CSP to allow serving images and iframes from backend

### 🐛 Fixed
- **Desktop**: Fix window hanging whilst waiting for backend startup
- **File Viewer**: Fix JSON parse error when backend returns non-JSON responses


## [v0.2.4] - 2026-02-08
### ⚡ Changed
- **Port**: use dynamic port for backend in release mode
- **Desktop App**: use pyinstaller for faster build

### 🐛 Fixed
- **Social Messaging**: fix social messaging setting's view crashes

## [v0.2.3] - 2026-02-03

### 🚀 Added
- **MCP**: Support headers for streamable-http MCP servers.
- **Context**: Add auto context compression.

### ⚡ Changed
- **MCP**: 
    - Move MCP server management from Config View to Settings View.
    - support headers for streamable-http MCP servers.
- **Refactor**: Refactor the settings view.
- **Browser**: Allow taking control of the internal browser.

### 🐛 Fixed
- **MCP**: Fix the frontend/backend inconsistency for MCP server.

## [v0.2.2] - 2026-02-02
### 🚀 Added
- **Browser**: Add browser tool and include a browser tab in the right sidebar.
- **Social Messaging Configuration**: Add social messaging configuration to the frontend.

### ⚡ Changed
- **UI**: Move the plan view to the bottom of the right sidebar.

### 🐛 Fixed
- **UX**: hide the progress bar when the right sidebar is expanded.
- **UI**: fix memory search cancel button displacement issue.

## [v0.2.1] - 2026-02-02

### ⚡ Changed
- **Frontend**: Move social message history to a separate tab.
- **Agent Manager**: Refactored to use a more robust agent management system.

## [v0.2.0] - 2026-02-01

### 🚀 Added
- **Social Messaging**: Full integration with major social platforms (Telegram, Slack, Discord, Feishu/Lark).
    - **Smart Routing**: The agent respects context—replying inside Threads, Channels, or Groups automatically.
    - **Multi-Modal**: Send text and files/images to the agent.
    - **Access Control**: Configure allowed users via `social.json`.
- **Tools**: Bash tool support in host mode.
- **UI**: Added "Open in File Explorer" option in file view.

### ⚡ Changed
- **Configuration**: Unified credentials management in `config/social.json`.
- **Core**: Enhanced driver stability for connection handling (Socket Mode for Slack, Polling for others).
- **Context**: Automatically injects the selected context folder into the system prompt.

### 🐛 Fixed
- **Routing**: Resolved "Reply in DM" routing bug.
- **Documentation**: Corrected privacy mode documentation for Telegram.
- **Code Quality**: Linting and formatting improvements.
- **Workflow**: Fixed upgrade workflow issues.
- **Rendering**: Resolved markdown code block rendering glitches.
- **Compatibility**: Fixed "path not found" errors on macOS.
- **Performance**: Optimized path resolver logic for sandbox/host mode.

## [v0.1.3]

### ⚡ Changed
- **Optimization**: Excluded heavy unused modules to prevent C compiler heap exhaustion during build.

### 🚀 Added
- **Releases**: Released standalone executable.

## [v0.1.2]

### 🚀 Added
- **Desktop App**: Initial desktop app release.
- **Configuration**:
    - Added API Models/Keys configuration UI.
    - Added Memory configuration UI.
- **UX**: Added context selector in chat box.
- **Files**: Unified file upload support for UI and Backend.
- **Distribution**: Added distribution packages and one-click scripts for Windows, Mac, and Linux.

### ⚠️ Deprecated
- **Modes**: Browser mode is now deprecated.
