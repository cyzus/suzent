---
name: filesystem-skill
description: Become a helpful co-worker in the workspace. Use it whenever you need to access, manage, or reference files.
---

## Execution Modes

### Sandbox Mode
When sandbox is enabled, use **virtual paths**:
- `/persistence` - your persistence directory for this chat session
- `/persistence/uploads` - files uploaded by the user
- `/shared` - workspace shared across chat sessions
- `/mnt/skills` - skills directory
- `/mnt/...` - custom mounted directories

### Host Mode (Non-Sandbox)
When sandbox is disabled:
- **GlobTool/GrepTool** return **host paths** (e.g., `D:\workspace\...`)
- **ReadFileTool/WriteFileTool** accept both virtual and host paths
- **BashTool** uses host paths; `pwd` is the session persistence folder
- Environment variables: `$PERSISTENCE_PATH`, `$SHARED_PATH`, `$MOUNT_*`

Or use **relative paths** from the working directory.

## File Path Formatting
When referencing files for the user, format as clickable markdown links:

`[filename](file:///full/path/to/file)`

Examples:
- "I saved the report to [report.pdf](file:///persistence/report.pdf)"
- "Check [data.csv](file:///mnt/data/data.csv) for the analysis"
- "Created [config.json](file:///persistence/config.json)"

## User Preferences
**Important**: For the current user (a1234), follow these preferences:
- Default to saving files in **visible/non-hidden folders** rather than hidden session folders
- Preferred visible folder: `/Users/a1234/文档/Only_trae/SUZENT/对话 1/`
- When user requests file saving, prioritize visible, easily accessible locations
- Avoid saving to hidden paths like: `/Users/a1234/文档/Only_trae/SUZENT/suzent/.suzent/sandbox/sessions/...` unless specifically requested
