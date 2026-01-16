---
name: notebook-skill
description: Gain access to the Obsidian notebook vault in /mnt/notebook.
---

# Notebook Skill

This skill enables skills-compatible agents to gain access to the user's Obsidian vault, create and edit valid Obsidian Flavored Markdown, including all Obsidian-specific syntax extensions.

## Directory Structure

The Obsidian vault is mounted at `/mnt/notebook`.

## Flavor

Obsidian uses a combination of Markdown flavors:
- [CommonMark](https://commonmark.org/)
- [GitHub Flavored Markdown](https://github.github.com/gfm/)
- [LaTeX](https://www.latex-project.org/) for math
- Obsidian-specific extensions (wikilinks, callouts, embeds, etc.)
