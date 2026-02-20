---
name: user-preferences
description: User-specific preferences and configurations for suzent
---

# User Preferences for a1234

## File Saving Preferences

### Default Behavior
- **Primary Preference**: Save files to visible/non-hidden folders by default
- **Avoid**: Hidden session folders unless explicitly requested

### Preferred Locations
1. **Primary visible folder**: `/Users/a1234/文档/Only_trae/SUZENT/对话 1/`
   - This is the main folder for user-created content
   - Easily accessible through file explorer

2. **Alternative visible folders** (if primary is unavailable):
   - `/Users/a1234/文档/Only_trae/SUZENT/` (root directory)
   - User's home directory or desktop

### Hidden Folders to Avoid
- `/Users/a1234/文档/Only_trae/SUZENT/suzent/.suzent/sandbox/sessions/...`
- Any path containing `.suzent` or other hidden directories

### Implementation Guidelines
1. When user requests file saving:
   - First check if primary visible folder exists and is writable
   - If not, use alternative visible locations
   - Only use hidden session folders as last resort or when explicitly requested

2. When suggesting file locations to user:
   - Always show visible folder paths first
   - Mark hidden paths as "session temporary" if mentioned

3. File naming:
   - Use descriptive names in Chinese or English
   - Include date if relevant (e.g., `报告_2026-02-20.md`)

### Examples
- Good: `"/Users/a1234/文档/Only_trae/SUZENT/对话 1/简短文章.md"`
- Avoid: `"/Users/a1234/文档/Only_trae/SUZENT/suzent/.suzent/sandbox/sessions/39742809-6375-4504-b1cf-07b8950b3d3d/简短文章.md"`

## Other User Preferences
*(To be added as more preferences are established)*

## Last Updated
- **Date**: 2026-02-20
- **Context**: User requested default file saving to visible folders
- **Applied by**: suzent assistant
