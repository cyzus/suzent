# Suzent Skills Guide

This guide covers the skills system in Suzent and how to use and create skills to extend agent capabilities.

## Overview

Skills are specialized knowledge modules that extend the capabilities of AI agents beyond what tools provide. While **tools** are executable functions (like web search or file operations), **skills** are contextual knowledge packages that teach the agent how to work in specific domains or with specific systems.

### Tools vs Skills

| Aspect | Tools | Skills |
|--------|-------|--------|
| **Purpose** | Execute actions | Provide knowledge & context |
| **Type** | Python code | Markdown documentation |
| **Examples** | WebSearchTool, BashTool | filesystem-skill, notebook-skill |
| **When Used** | Agent calls them to perform tasks | Agent loads them to gain expertise |

## Available Skills

Suzent includes two built-in skills:

### 1. filesystem-skill

Provides information about the workspace directory structure for agents working in the sandbox environment.

**Key Information:**
- `/persistence` - Per-chat session directory
- `/shared` - Workspace shared across all chat sessions
- `/mnt/skills` - Skills directory
- `/mnt/...` - Other mounted directories

### 2. notebook-skill

Enables agents to work with Obsidian vaults, understanding Obsidian Flavored Markdown syntax.

**Key Information:**
- Vault location: `/mnt/notebook`
- Supports CommonMark, GitHub Flavored Markdown, LaTeX math
- Handles Obsidian-specific extensions (wikilinks, callouts, embeds)

## Skill Structure

Each skill is a directory containing a `SKILL.md` file and optional resource folders.

### Directory Layout

```
~/.suzent/skills/
├── official/             # Synced from the repo's built-in skills
├── external/             # Synced from SKILLS_DIR, grouped by source
└── user/
    └── my-skill/
        ├── SKILL.md      # Required: Main skill definition
        ├── scripts/      # Optional: Helper scripts
        ├── references/   # Optional: Reference documents
        └── assets/       # Optional: Images, data files
```

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
    "notebook-skill",
    "filesystem-skill"
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

### Skill Mounting in Sandbox

Skills are automatically mounted in the sandbox under `/mnt/skills/`:

```
/mnt/skills/
├── official/
│   ├── filesystem/
│   │   └── SKILL.md
│   └── notebook/
│       └── SKILL.md
├── external/
│   └── my-pack-abc12345/
│       └── custom-skill/
│           └── SKILL.md
└── user/
    └── my-custom-skill/
        └── SKILL.md
```

## Creating Custom Skills

### Step 1: Create Skill Directory

Create a new directory in `~/.suzent/skills/user/`:

```bash
mkdir -p ~/.suzent/skills/user/my-custom-skill
```

### Step 2: Create SKILL.md

Create `~/.suzent/skills/user/my-custom-skill/SKILL.md`:

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
mkdir ~/.suzent/skills/user/my-custom-skill/scripts
echo "#!/bin/bash\necho 'Helper script'" > ~/.suzent/skills/user/my-custom-skill/scripts/helper.sh

# Add reference documentation
mkdir ~/.suzent/skills/user/my-custom-skill/references
cp ~/docs/api-reference.md ~/.suzent/skills/user/my-custom-skill/references/
```

### Step 4: Enable the Skill

Add your skill to `~/.suzent/config/skills.json`:

```json
{
  "enabled": [
    "notebook-skill",
    "filesystem-skill",
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

- **Built-in Skills Directory**: `./skills/`, synced to `~/.suzent/skills/official/`
- **User Skills Directory**: `~/.suzent/skills/user/`
- **External Skills Directory**: `~/.suzent/skills/external/`
- **Config File**: `~/.suzent/config/skills.json`
- **Sandbox Mount**: `/mnt/skills/`

### Environment Variables

```bash
# Advanced extra skills directory, synced into ~/.suzent/skills/external/
SKILLS_DIR=/path/to/custom/skills
```

### Reloading Skills

Skills are loaded at startup. To reload:
1. Modify `~/.suzent/config/skills.json`
2. Restart the Suzent server

### Skill Discovery

The SkillManager automatically discovers skills by:
1. Syncing built-in skills to `official/` and optional `SKILLS_DIR` roots to `external/`
2. Scanning official, external, and user skills in that order
3. Looking for `SKILL.md` files
4. Parsing YAML frontmatter
5. Validating required fields

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
4. Resources are mounted under the skill's listed location, such as `/mnt/skills/user/{skill-name}/`

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
- `BashTool` enabled (for running scripts)
- `filesystem-skill` loaded (for workspace navigation)
- Python 3.8+ installed in sandbox
```
