# Suzent Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
