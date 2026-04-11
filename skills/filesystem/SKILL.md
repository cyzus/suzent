---
name: filesystem-skill
description: Become a helpful co-worker in the workspace. Use it whenever you need to access, manage, or reference files.
---

## Execution Modes

### Host Mode
You are running directly on the host machine.
- **Environment Variables**: Use standard locations via environment variables:
  - Windows: `%PERSISTENCE_PATH%`, `%SHARED_PATH%`, `%MOUNT_SKILLS%`
  - POSIX: `$PERSISTENCE_PATH`, `$SHARED_PATH`, `$MOUNT_SKILLS`
- **Host Paths**: `GlobTool` and `GrepTool` return absolute host paths (e.g., `D:\workspace\...`). Use them directly.
- **Tools**: `ReadFileTool`, `WriteFileTool`, and `BashTool` all accept host paths.

### Sandbox Mode (Isolated)
When sandbox is enabled, you MUST use **virtual paths**:
- `/persistence` - session private directory
- `/shared` - workspace shared across sessions
- `/mnt/skills` - skills directory
- `/mnt/...` - other mapped volumes

> [!WARNING]
> Do NOT use `/mnt/...` paths in Host Mode as they will not exist. Always check your execution mode in the system instructions.

## File Path Formatting
When referencing files for the user, format as clickable markdown links:

`[filename](file:///full/path/to/file)`

Examples:
- "I saved the report to [report.pdf](file:///D:/workspace/report.pdf)" (Host example)
- "Check [data.csv](file:///persistence/data.csv) for the analysis" (Sandbox example)
- "Created [config.json](file:///shared/config.json)" (Sandbox example)

