# Documentation

## Getting Started
- [What is Suzent?](01-getting-started/intro.md): Core concepts and architecture overview
- [Quickstart](01-getting-started/quickstart.md): Set up Suzent from scratch in under 5 minutes

## Concepts

### Core
- [Providers](02-concepts/providers/README.md): Configure model providers (OpenAI, Anthropic, Gemini, Ollama, and more)
- [Memory](02-concepts/memory/README.md): Persistent memory across sessions — how it works and how to configure it
- [LLM Wiki](02-concepts/memory/llm-wiki.md): Agent-maintained structured knowledge vault

### Tools & Capabilities
- [Tools](02-concepts/tools/tools.md): Full reference for all built-in tools
- [Canvas (A2UI)](02-concepts/tools/canvas.md): Interactive UI components rendered in the sidebar
- [Tool Approval](02-concepts/tools/human-in-the-loop.md): How dangerous tools require user confirmation
- [Skills](02-concepts/skills/skills.md): Extend the agent with domain knowledge modules
- [Filesystem & Sandbox](02-concepts/filesystem.md): File access, sandbox execution, and storage paths

### Automation & Connectivity
- [Automation](02-concepts/automation/automation.md): Cron jobs and heartbeat monitoring
- [GitHub Sync](02-concepts/github-sync/README.md): Sync portable brain data to a private GitHub repo
- [Social Messaging](02-concepts/social-messaging/README.md): Telegram, Discord, Slack, and Feishu integration
- [Nodes](02-concepts/nodes/nodes.md): Connect and control companion devices remotely

### Runtime
- [Retry](02-concepts/runtime/retry.md): Roll back the last agent turn and rerun
- [Post-Processing](02-concepts/runtime/postprocess.md): Background tasks after each turn

## Development
- [Development Guide](03-developing/development-guide.md): Setup, workflow, production builds, and architecture
- [Docker Services](03-developing/docker-services.md): Redis, SearXNG, and sandbox configuration
- [Release Guide](03-developing/releasing.md): Version bumping and release process
- [Memory Internals](02-concepts/memory/internals.md): Memory system architecture for contributors
- [Logo Standard](03-developing/logo.md): Canonical logo geometry, component usage, and sizing guidelines
