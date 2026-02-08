# Suzent Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.5]
### 🐛 Fixed
- **Desktop**: fix window hanging whilst waiting for backend startup


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
