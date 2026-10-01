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

- [Models & Providers](./04-models/README.md): connect OpenAI, Anthropic, Gemini, Ollama, and more, one page per provider
  - [Model roles](./04-models/model-roles.md): choose which model does which job
- [Memory](./03-features/memory/README.md): what your agent remembers, where it lives, and how to change it
  - [Notebook](./03-features/memory/llm-wiki.md): the Obsidian-compatible knowledge vault
  - [Advanced memory settings](./03-features/memory/configuration.md)
- [Tools](./03-features/tools/tools.md): everything your agent can do, and how to turn it on or off
  - [Permissions & approvals](./03-features/tools/human-in-the-loop.md): how Suzent asks before it acts
  - [Browser](./03-features/tools/browser.md): its own browser, or yours through the extension
- [Skills](./03-features/skills.md): install, write, and manage `SKILL.md` packages
- [Workspace & sandbox](./03-features/filesystem.md): folders, the Docker sandbox, and undoing a turn
- [Automation](./03-features/automation.md): scheduled tasks, heartbeats, goals, and the background service
- [Chat apps](./05-chat-apps/README.md): Telegram, Slack, Discord, Feishu, and WeChat, one page per app
- [Devices & other agents](./03-features/nodes.md): your phone, other computers, A2A agents, and your editor
- [GitHub Sync](./03-features/github-sync.md): carry your agent to another computer

## Development

For contributors working on Suzent's own code. You don't need any of this to use Suzent.
Pages here describe what exists today; planned work lives in the
[Roadmap](./08-developing/roadmap.md).

**Contributing**: [Development guide](./08-developing/contributing/development-guide.md), [Web UI](./08-developing/contributing/web-ui.md), [Docker services](./08-developing/contributing/docker-services.md), [Releasing](./08-developing/contributing/releasing.md), [Mobile releases](./08-developing/contributing/mobile-releases.md), [Updating model capabilities](./08-developing/contributing/model-capability-updates.md)

**Architecture**: [Tool system](./08-developing/architecture/tool-system.md), [Canvas (A2UI)](./08-developing/architecture/canvas.md), [Agent communication](./08-developing/architecture/agent-inbox.md), [System reminders](./08-developing/architecture/system-reminders.md), [Post-processing](./08-developing/architecture/postprocess.md), [Stream recovery](./08-developing/architecture/stream-recovery-protocol.md), [Memory architecture](./08-developing/architecture/memory-architecture.md), [Memory internals](./08-developing/architecture/memory-internals.md), [Model capabilities](./08-developing/architecture/model-capabilities.md), [Native mobile](./08-developing/architecture/mobile.md)

**Protocols & APIs**: [HTTP API](./08-developing/protocols/http-api.md), [Node protocol](./08-developing/protocols/node-protocol.md), [Node security](./08-developing/protocols/node-security.md), [A2A](./08-developing/protocols/a2a.md), [ACP](./08-developing/protocols/acp.md)
