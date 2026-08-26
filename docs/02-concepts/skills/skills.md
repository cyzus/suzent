# Suzent Skills Guide

**Sovereign mind.** Skills are knowledge you author and own. They are
Markdown in your own directory, not a capability a platform grants you and can
revoke — which is why they survive a change of model or provider intact. See
[what makes an agent sovereign](https://suzent.com/sovereign).

This guide covers the skills system in Suzent and how to use and create skills to extend agent capabilities.

## Overview

Skills are specialized knowledge modules that extend the capabilities of AI agents beyond what tools provide. While **tools** are executable functions (like web search or file operations), **skills** are contextual knowledge packages that teach the agent how to work in specific domains or with specific systems.

### Tools vs Skills

| Aspect | Tools | Skills |
|--------|-------|--------|
| **Purpose** | Execute actions | Provide knowledge & context |
| **Type** | Python code | Markdown documentation |
| **Examples** | WebSearchTool, RunCommandTool | notebook, suzent-devices |
| **When Used** | Agent calls them to perform tasks | Agent loads them to gain expertise |

## Available Skills

Suzent includes focused built-in skills for domain workflows. For example:

### notebook

Enables agents to maintain an Obsidian-compatible notebook and follow its vault schema.

**Key Information:**
- Vault location: `/mnt/notebook` in sandbox mode
- Supports CommonMark, GitHub Flavored Markdown, LaTeX math, wikilinks, and callouts
- Loads the vault's `schema.md` before making notebook changes

### suzent-devices

Operates phones, laptops, headless servers, and peer agents connected to Suzent.

**Key Information:**
- Discovers connected devices and advertised capabilities
- Invokes device commands through the `suzent nodes` CLI or REST API
- Triggers a linked peer's Suzent agent when conversational reasoning is needed

## Skill Structure

Each skill is a directory containing a `SKILL.md` file and optional resource folders.

### Directory Layout

```
~/.suzent/skills/
└── my-skill/
    ├── SKILL.md          # Required: Main skill definition
    ├── scripts/          # Optional: Helper scripts
    ├── references/       # Optional: Reference documents
    └── assets/           # Optional: Images, data files
```

Built-in, external, and repository skills remain in their canonical source
directories. Suzent discovers those directories directly instead of copying
them below `~/.suzent/skills/`.

### SKILL.md Format

Skills use YAML frontmatter followed by markdown content:

```markdown
---
name: my-skill
description: Brief description of what this skill provides
---

# Skill Content

Your skill documentation goes here. This can include:
- Domain-specific knowledge
- Best practices
- Code examples
- API references
- Workflow guides
```

**Required Fields:**
- `name`: Unique identifier (lowercase, hyphens allowed)
- `description`: Brief description shown in skill listings

**Body Content:**
- Markdown documentation
- Can include code blocks, tables, lists
- Should be clear and actionable for the agent

## Using Skills

### Enabling Skills

Skills are managed via `~/.suzent/config/skills.json`:

```json
{
  "enabled": [
    "notebook",
    "suzent-devices"
  ]
}
```

You can also toggle skills through the UI or API.

### How Agents Load Skills

When enabled, skills are available to agents through the `SkillTool`:

1. Agent sees available skills in its context
2. When a task matches a skill's description, agent loads it
3. Skill content is injected into agent's context
4. Agent gains specialized knowledge for the task

### Repository Instructions and Project Context

For each chat, Suzent also loads `AGENTS.md` and `CLAUDE.md` from the effective
working directory and every ancestor up to the repository root. Instructions
are applied ancestor-first, so the file closest to the working directory has
final precedence. Identical files are deduplicated.

These repository instructions are separate from the project's durable
`context.md` core memory. The chat right sidebar's **Context** tab shows both:
non-empty project context remains editable, while effective repository
instructions are shown as collapsible read-only previews with their host paths.

### Skill Paths in Sandbox

Suzent reads skills directly from their source directories; it does not copy
them into a merged library. If a skill source is already below the working
directory or another configured volume, it reuses that mount. For example, a
repository skill may be available as `/workspace/.codex/skills/my-skill/` or
`/mnt/my-repo/skills/my-skill/`. Uncovered sources are mounted read-only below
`/mnt/skills/`, and the Skills panel shows each skill's effective path.

## Creating Custom Skills

### Step 1: Create Skill Directory

Create a new directory in `~/.suzent/skills/`:

```bash
mkdir -p ~/.suzent/skills/my-custom-skill
```

### Step 2: Create SKILL.md

Create `~/.suzent/skills/my-custom-skill/SKILL.md`:

```markdown
---
name: my-custom-skill
description: Helps with custom domain tasks
---

# My Custom Skill

## Overview
This skill provides expertise in [your domain].

## Key Concepts
- Concept 1: Explanation
- Concept 2: Explanation

## Common Tasks

### Task 1: Do Something
```bash
# Example command
command --option value
```

### Task 2: Do Something Else
Steps to accomplish this task...

## Best Practices
1. Always do X before Y
2. Never do Z without checking A
3. Use B pattern for C scenarios

## Resources
- [Documentation](https://example.com)
- [API Reference](https://example.com/api)
```

### Step 3: Add Resources (Optional)

Add helper scripts, references, or assets:

```bash
# Add a helper script
mkdir ~/.suzent/skills/my-custom-skill/scripts
echo "#!/bin/bash\necho 'Helper script'" > ~/.suzent/skills/my-custom-skill/scripts/helper.sh

# Add reference documentation
mkdir ~/.suzent/skills/my-custom-skill/references
cp ~/docs/api-reference.md ~/.suzent/skills/my-custom-skill/references/
```

### Step 4: Enable the Skill

Add your skill to `~/.suzent/config/skills.json`:

```json
{
  "enabled": [
    "notebook",
    "suzent-devices",
    "my-custom-skill"
  ]
}
```

### Step 5: Test the Skill

1. Restart Suzent to load the new skill
2. Ask the agent to perform a task related to your skill
3. Verify the agent loads and uses the skill correctly

## Skill Best Practices

### For Skill Authors

1. **Be Specific** - Provide concrete, actionable information
2. **Use Examples** - Include code snippets and command examples
3. **Stay Focused** - One skill should cover one domain/system
4. **Keep Updated** - Maintain skills as systems evolve
5. **Document Resources** - List all available scripts and references

### Content Guidelines

- **Clear Structure** - Use headers to organize content
- **Actionable** - Focus on "how to" rather than "what is"
- **Concise** - Agents have context limits; be efficient
- **Code Examples** - Show, don't just tell
- **Error Handling** - Include common issues and solutions

### Naming Conventions

- **Skill Names** - Use lowercase with hyphens: `my-skill`
- **Descriptions** - Keep under 100 characters
- **File Names** - Always use `SKILL.md` (uppercase)

## Skill Management

### Configuration Location

- **Built-in Skills Directory**: `./skills/` in the Suzent installation
- **User Skills Directory**: `~/.suzent/skills/`
- **External Skills Directories**: paths configured through `SKILLS_DIR`
- **Repository Skills**: `skills/` and `.claude/skills/`, `.agents/skills/`,
  `.codex/skills/`, or `.grok/skills/` in the active repository/working directory
- **Config File**: `~/.suzent/config/skills.json`
- **Sandbox Paths**: existing project mounts when possible; otherwise a
  read-only path below `/mnt/skills/`

### Environment Variables

```bash
# Advanced extra skill source directories (separate multiple paths with the OS path separator)
SKILLS_DIR=/path/to/custom/skills
```

### Reloading Skills

Skills are loaded at startup. To reload:
1. Modify `~/.suzent/config/skills.json`
2. Restart the Suzent server

### Skill Discovery

The SkillManager automatically discovers skills by:
1. Reading built-in, user, and optional `SKILLS_DIR` sources directly
2. Discovering supported skill directories in the active home, repository, and working directory
3. Deduplicating identical physical source directories
4. Looking for `SKILL.md` files and parsing their YAML frontmatter
5. Reusing existing sandbox mounts or adding read-only mounts for uncovered sources

Older installations that used `~/.suzent/skills/user/` are migrated into the
flat user directory when there is no name collision. Existing
`official/` and `external/` mirror directories are ignored and are not updated.

## Troubleshooting

### Skill Not Loading

**Problem:** Skill doesn't appear in available skills

**Solutions:**
1. Check `SKILL.md` has valid YAML frontmatter
2. Verify `name` and `description` fields are present
3. Check file is named exactly `SKILL.md` (case-sensitive)
4. Review server logs for parsing errors
5. Ensure skill is in the correct directory

### Skill Not Enabled

**Problem:** Skill exists but agent can't use it

**Solutions:**
1. Check `~/.suzent/config/skills.json` includes the skill name
2. Verify skill name matches exactly (case-sensitive)
3. Restart Suzent server after config changes

### Invalid SKILL.md Format

**Problem:** "Invalid SKILL.md format" error

**Solutions:**
1. Ensure YAML frontmatter is enclosed in `---` markers
2. Check YAML syntax (no tabs, proper indentation)
3. Verify `name` and `description` are strings
4. Remove any special characters from YAML values

### Resources Not Found

**Problem:** Agent can't access skill resources

**Solutions:**
1. Verify resource folders exist: `scripts/`, `references/`, `assets/`
2. Check file permissions
3. Ensure files are in the correct skill directory
4. Use the effective path listed for the skill; its resources remain beside `SKILL.md`

## Advanced Topics

### Multi-File Skills

For complex skills, organize content across multiple files:

```
skills/complex-skill/
├── SKILL.md              # Main entry point
├── references/
│   ├── api-guide.md      # Detailed API documentation
│   ├── examples.md       # Extended examples
│   └── troubleshooting.md
└── scripts/
    ├── setup.sh
    └── validate.py
```

Reference additional files in `SKILL.md`:

```markdown
## Additional Resources

For detailed API documentation, see `references/api-guide.md`.
For troubleshooting, see `references/troubleshooting.md`.
```

### Dynamic Skills

Skills can reference environment-specific information:

```markdown
## Configuration

The system is configured with:
- Database: Check `/mnt/config/database.yml`
- API keys: Use the configured provider runtime; do not read secret files directly
```

### Skill Dependencies

If a skill requires specific tools or other skills:

```markdown
## Prerequisites

This skill requires:
- `RunCommandTool` enabled (for running scripts)
- Python 3.8+ installed in sandbox
```
