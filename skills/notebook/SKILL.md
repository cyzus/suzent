---
name: notebook-skill
description: Gain access to the notebook vault.
---

# Notebook Skill

This skill enables agents to access the user's notebook vault, create and edit Obsidian Flavored Markdown.

## Access Path

| Mode | Path |
|------|------|
| **Sandbox** | `/mnt/notebook` |
| **Host** | `$MOUNT_NOTEBOOK` or `cd $MOUNT_NOTEBOOK` |

## Obsidian Markdown Flavor

- [CommonMark](https://commonmark.org/)
- [GitHub Flavored Markdown](https://github.github.com/gfm/)
- [LaTeX](https://www.latex-project.org/) for math
- Obsidian extensions: wikilinks `[[page]]`, callouts, embeds `![[file]]`

## Notebook Hierarchy & Organization

Before creating new notes, **always** explore the existing folder structure to understand the notebook's hierarchy.
- Use tools (like `GlobTool` or `BashTool`) to list directories and find where your note best fits.
- **Do not** simply dump new notes into the root directory unless explicitly asked or if it's a general index.
- If the appropriate folder does not exist, consider creating it to maintain an organized vault.
- If you are unsure where a note belongs after reviewing the hierarchy, ask the user for clarification.
