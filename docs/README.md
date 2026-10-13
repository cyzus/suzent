# Documentation

Suzent is a sovereign AI agent: an open-source, local-first agent whose identity,
memory, skills, workspace, and runtime stay under your control, independent of
any model or platform. For the definition of agent sovereignty and the
five-question ownership test, see
[what makes an agent sovereign](https://suzent.com/sovereign).

## Getting Started

- [What is Suzent?](01-getting-started/intro.md): what a sovereign agent is and what Suzent can do
- [Quickstart](01-getting-started/quickstart.md): install, connect a model, and start chatting
- [Desktop, phone, and browser](01-getting-started/platforms.md): every way to reach your agent
- [Updating](01-getting-started/updating.md): update Suzent and upgrade an existing install

## Using Suzent

- [Working with your agent](02-using/conversations.md), [Organizing work into projects](02-using/projects.md), [Making it yours](02-using/make-it-yours.md)

## Features

- [Overview](03-features/README.md)
- [Memory](03-features/memory/README.md), [Notebook](03-features/memory/llm-wiki.md), [Advanced memory settings](03-features/memory/configuration.md)
- [Tools](03-features/tools/README.md), [Permissions & approvals](03-features/tools/human-in-the-loop.md), [Browser](03-features/tools/browser.md)
- [Skills](03-features/skills.md), [Workspace & sandbox](03-features/filesystem.md), [Automation](03-features/automation.md)
- [Devices & other agents](03-features/nodes.md), [GitHub Sync](03-features/github-sync.md)

## Models

- [Models & Providers](04-models/README.md) and [Model roles](04-models/model-roles.md)
- Cloud: [OpenAI](04-models/cloud/openai.md), [ChatGPT Subscription](04-models/cloud/chatgpt-subscription.md), [Anthropic](04-models/cloud/anthropic.md), [Google Gemini](04-models/cloud/gemini.md), [xAI](04-models/cloud/xai.md), [DeepSeek](04-models/cloud/deepseek.md), [DashScope](04-models/cloud/dashscope.md), [Moonshot](04-models/cloud/moonshot.md), [Zhipu AI](04-models/cloud/zhipu.md), [MiniMax](04-models/cloud/minimax.md), [Xiaomi MiMo](04-models/cloud/xiaomi-mimo.md), [OpenRouter](04-models/cloud/openrouter.md)
- Local and self-hosted: [Ollama](04-models/local/ollama.md), [vLLM](04-models/local/vllm.md), [SGLang](04-models/local/sglang.md), [LiteLLM Proxy](04-models/local/litellm.md)

## Chat apps

- [Overview](05-chat-apps/README.md) and [Access control & pairing](05-chat-apps/access-control.md)
- [Telegram](05-chat-apps/telegram.md), [Slack](05-chat-apps/slack.md), [Discord](05-chat-apps/discord.md), [Feishu (Lark)](05-chat-apps/feishu.md), [WeChat](05-chat-apps/wechat.md)

## Tutorials

- [Run everything on your own computer](06-tutorials/run-locally.md)
- [Get a morning briefing on Telegram](06-tutorials/morning-briefing.md)
- [Work on a folder safely](06-tutorials/project-folder.md)

## Reference

- [Command line](07-reference/cli.md), [Slash commands](07-reference/slash-commands.md), [Settings pages](07-reference/settings.md), [Configuration files](07-reference/configuration.md), [FAQ & troubleshooting](07-reference/faq.md)

## Development

For contributors working on Suzent's own code. You don't need any of this to use Suzent.
Pages here describe what exists today; planned work lives in the
[Roadmap](./08-developing/roadmap.md).

**Contributing**: [Development guide](./08-developing/contributing/development-guide.md), [Web UI](./08-developing/contributing/web-ui.md), [Docker services](./08-developing/contributing/docker-services.md), [Releasing](./08-developing/contributing/releasing.md), [Mobile releases](./08-developing/contributing/mobile-releases.md), [Updating model capabilities](./08-developing/contributing/model-capability-updates.md)

**Architecture**: [Tool system](./08-developing/architecture/tool-system.md), [Canvas (A2UI)](./08-developing/architecture/canvas.md), [Agent communication](./08-developing/architecture/agent-inbox.md), [System reminders](./08-developing/architecture/system-reminders.md), [Post-processing](./08-developing/architecture/postprocess.md), [Stream recovery](./08-developing/architecture/stream-recovery-protocol.md), [Memory architecture](./08-developing/architecture/memory-architecture.md), [Memory internals](./08-developing/architecture/memory-internals.md), [Model capabilities](./08-developing/architecture/model-capabilities.md), [Native mobile](./08-developing/architecture/mobile.md)

**Protocols & APIs**: [HTTP API](./08-developing/protocols/http-api.md), [Node protocol](./08-developing/protocols/node-protocol.md), [Node security](./08-developing/protocols/node-security.md), [A2A](./08-developing/protocols/a2a.md), [ACP](./08-developing/protocols/acp.md)
