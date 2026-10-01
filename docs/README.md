# Documentation

Suzent is a sovereign AI agent: an open-source, local-first agent whose identity,
memory, skills, workspace, and runtime stay under your control, independent of
any model or platform. For the definition of agent sovereignty and the
five-question ownership test, see
[what makes an agent sovereign](https://suzent.com/sovereign).

## Getting Started

- [What is Suzent?](01-getting-started/intro.md): what a sovereign agent is and what Suzent can do
- [Quickstart](01-getting-started/quickstart.md): install, connect a model, and start chatting
- [Updating](01-getting-started/updating.md): update Suzent and upgrade an existing install

## Guides

- [Models & Providers](02-concepts/providers.md): connect OpenAI, Anthropic, Gemini, Ollama, and more, and assign models to jobs
- [Memory](02-concepts/memory/README.md): what your agent remembers, where it lives, and how to change it
  - [Notebook](02-concepts/memory/llm-wiki.md): the Obsidian-compatible knowledge vault
  - [Advanced memory settings](02-concepts/memory/configuration.md)
- [Tools](02-concepts/tools/tools.md): everything your agent can do, and how to turn it on or off
  - [Permissions & approvals](02-concepts/tools/human-in-the-loop.md): how Suzent asks before it acts
  - [Browser](02-concepts/tools/browser.md): its own browser, or yours through the extension
- [Skills](02-concepts/skills.md): install, write, and manage `SKILL.md` packages
- [Workspace & sandbox](02-concepts/filesystem.md): folders, the Docker sandbox, and undoing a turn
- [Automation](02-concepts/automation.md): scheduled tasks, heartbeats, goals, and the background service
- [Chat apps](02-concepts/social-messaging.md): Telegram, Slack, Discord, Feishu, and WeChat
- [Devices & other agents](02-concepts/nodes.md): your phone, other computers, A2A agents, and your editor
- [GitHub Sync](02-concepts/github-sync.md): carry your agent to another computer

## Development

For contributors working on Suzent's own code. You don't need any of this to use Suzent.

- [Development Guide](03-developing/development-guide.md): setup, workflow, production builds, and architecture
- [Web UI](03-developing/web-ui.md), [Docker Services](03-developing/docker-services.md), [Release Guide](03-developing/releasing.md), [Native Mobile](03-developing/mobile.md)
- [HTTP API and internals](03-developing/http-api.md), [Tool system](03-developing/tool-system.md), [Canvas (A2UI)](03-developing/canvas.md)
- [Node protocol](03-developing/node-protocol.md), [Node security](03-developing/node-security.md), [A2A](03-developing/a2a.md), [ACP](03-developing/acp.md)
- [Memory architecture](03-developing/memory-architecture.md), [Memory internals](03-developing/memory-internals.md)
- [Model capabilities and roles](03-developing/model-capabilities.md), [Stream recovery protocol](03-developing/stream-recovery-protocol.md)
