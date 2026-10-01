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

- [Models & Providers](02-concepts/providers/README.md): connect OpenAI, Anthropic, Gemini, Ollama, and more, one page per provider
  - [Model roles](02-concepts/providers/model-roles.md): choose which model does which job
- [Memory](02-concepts/memory/README.md): what your agent remembers, where it lives, and how to change it
  - [Notebook](02-concepts/memory/llm-wiki.md): the Obsidian-compatible knowledge vault
  - [Advanced memory settings](02-concepts/memory/configuration.md)
- [Tools](02-concepts/tools/tools.md): everything your agent can do, and how to turn it on or off
  - [Permissions & approvals](02-concepts/tools/human-in-the-loop.md): how Suzent asks before it acts
  - [Browser](02-concepts/tools/browser.md): its own browser, or yours through the extension
- [Skills](02-concepts/skills.md): install, write, and manage `SKILL.md` packages
- [Workspace & sandbox](02-concepts/filesystem.md): folders, the Docker sandbox, and undoing a turn
- [Automation](02-concepts/automation.md): scheduled tasks, heartbeats, goals, and the background service
- [Chat apps](02-concepts/social-messaging/README.md): Telegram, Slack, Discord, Feishu, and WeChat, one page per app
- [Devices & other agents](02-concepts/nodes.md): your phone, other computers, A2A agents, and your editor
- [GitHub Sync](02-concepts/github-sync.md): carry your agent to another computer

## Development

For contributors working on Suzent's own code. You don't need any of this to use Suzent.
Pages here describe what exists today; planned work lives in the
[Roadmap](./03-developing/roadmap.md).

**Contributing**: [Development guide](./03-developing/contributing/development-guide.md), [Web UI](./03-developing/contributing/web-ui.md), [Docker services](./03-developing/contributing/docker-services.md), [Releasing](./03-developing/contributing/releasing.md), [Mobile releases](./03-developing/contributing/mobile-releases.md), [Updating model capabilities](./03-developing/contributing/model-capability-updates.md)

**Architecture**: [Tool system](./03-developing/architecture/tool-system.md), [Canvas (A2UI)](./03-developing/architecture/canvas.md), [Agent communication](./03-developing/architecture/agent-inbox.md), [System reminders](./03-developing/architecture/system-reminders.md), [Post-processing](./03-developing/architecture/postprocess.md), [Stream recovery](./03-developing/architecture/stream-recovery-protocol.md), [Memory architecture](./03-developing/architecture/memory-architecture.md), [Memory internals](./03-developing/architecture/memory-internals.md), [Model capabilities](./03-developing/architecture/model-capabilities.md), [Native mobile](./03-developing/architecture/mobile.md)

**Protocols & APIs**: [HTTP API](./03-developing/protocols/http-api.md), [Node protocol](./03-developing/protocols/node-protocol.md), [Node security](./03-developing/protocols/node-security.md), [A2A](./03-developing/protocols/a2a.md), [ACP](./03-developing/protocols/acp.md)
