<div align="right">

*[中文版](README.zh-CN.md)*

</div>

<div align="center">

![Suzent Banner](docs/assets/banner_v2.png)

# **SUZENT: THE SOVEREIGN AI AGENT**

### **YOUR AGENT SHOULD NOT BE AN ACCOUNT YOU RENT.**

![Status](https://img.shields.io/badge/RITUAL-READY-black?style=flat-square) ![System](https://img.shields.io/badge/GEIST-LOCAL_FIRST-black?style=flat-square)

[![Version](https://img.shields.io/github/v/release/cyzus/suzent?style=flat-square&label=version)](https://github.com/cyzus/suzent/releases) [![License](https://img.shields.io/github/license/cyzus/suzent?style=flat-square)](LICENSE) [![Python](https://img.shields.io/badge/python-3.12%2B-yellow?style=flat-square)](https://python.org) [![Discord](https://img.shields.io/badge/Discord-Join%20Chat-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/MkBDDbwPBK)


**[WEBSITE](https://suzent.com)** • **[SUMMONING RITUAL](docs/01-getting-started/quickstart.md)** • **[GRIMOIRE](docs/README.md)** • **[CONTRIBUTING](./CONTRIBUTING.md)**



</div>

---

## <img src="docs/assets/robot-idle.svg" width="30" style="vertical-align: middle;" /> **SUMMON A SOVEREIGN GEIST**

> Your agent should not be an account you rent. It should be a system you own.

**SUZENT** [soo-zuh-nt] is an open-source, local-first AI agent whose identity, memory, skills, workspace, and runtime remain under your control. Use GPT, Claude, Gemini, DeepSeek, local models, or whatever comes next without resetting the agent that knows you and your work.

Its memory is append-only Markdown on your disk, not rows in someone else's database. Its tool calls pass through permission modes you define. Its execution is isolated in Docker workspaces you own. It can research, write, code, pursue goals, run scheduled work, connect to your devices, and meet you in Telegram, Slack, Discord, Feishu, or WeChat — always inside boundaries you set.

**Models are replaceable. Platforms are temporary. Your agent remains.**

---

## **QUICK START**

### **INSTALL**

SUZENT runs on Windows, macOS, and Linux. One command summons it, its Python backend, and the `suzent` CLI. Git is the only prerequisite; everything else is auto-installed.

**macOS / Linux**
```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

**Windows** (PowerShell)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

**Mainland China mirror mode**
```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | SUZENT_CHINA_MIRROR=1 bash
```

```powershell
$env:SUZENT_CHINA_MIRROR="1"; powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

This uses faster mirrors for PyPI, npm, Playwright, Node via nvm, and Rustup. If GitHub itself is slow, set `SUZENT_REPO_URL` or `SUZENT_RELEASE_BASE_URL` to a mirror you trust before running the command.

Then bind your keys in `~/suzent/.env` and run:

```bash
suzent start
```

### **THE `suzent` CLI**

```bash
suzent start           # Start the backend and the desktop app
suzent serve           # Start the backend only (headless / standalone)
suzent ui              # Start the desktop app against a running backend
suzent stop            # Stop a running backend server
suzent doctor          # Check requirements and diagnose a broken install
suzent update          # Update to the latest stable release
suzent check-update    # Report whether a newer release exists
suzent repair          # Recover an interrupted or damaged update
```

Run `suzent --help`, or `suzent <command> --help`, for the full flag set.

### **UPDATE**

```bash
suzent update
```

This installs the latest stable release as one matched set: backend source, locked dependencies, and desktop app. A standalone updater performs the switch outside the active virtual environment, verifies downloaded assets, and rolls back automatically on failure. If an interrupted update needs recovery, run:

```bash
suzent repair
```

Developers working from a source checkout can update `main` and its frontend dependencies together with plain `suzent update`; the checkout is detected automatically. The explicit equivalent is:

```bash
suzent update --dev
```

Or re-run the install command above — it detects an existing installation and updates it to the latest stable release.

---

## **WHAT MAKES AN AGENT SOVEREIGN?**

| Question | SUZENT's answer |
|---|---|
| Who owns its memory? | **You.** Markdown files are the durable source of truth. |
| Who chooses its intelligence? | **You.** Models and providers are replaceable. |
| Who defines what it may do? | **You.** Permissions, rules, and sandbox boundaries are explicit. |
| Where does it live? | **On infrastructure you control.** |
| Can it move? | Memory, skills, and configuration are portable; credentials stay local. |
| Can you inspect it? | Tool calls, authorization decisions, files, and memory remain visible. |

Sovereignty is not merely local execution. It is ownership of the agent's **mind, authority, vessel, and continuity**.

## **THE SOVEREIGN SYSTEM**

### <img src="docs/assets/robot-agnostic.svg" width="28" style="vertical-align: middle;" /> **CHOOSE ITS INTELLIGENCE**

Models are engines, not identities. Switch between GPT, Claude, Gemini, DeepSeek, local models, and compatible providers without surrendering the memory, skills, or workspace that make the agent yours.

### <img src="docs/assets/robot-thinking.svg" width="28" style="vertical-align: middle;" /> **OWN ITS MEMORY**

Conversation facts land in append-only Markdown logs, consolidate into an inspectable notebook, and are indexed for semantic recall—the files stay authoritative, and the LanceDB index can be rebuilt from them at any time. Read, edit, delete, version, and carry that memory yourself.

### <img src="docs/assets/robot-snooze.svg" width="28" style="vertical-align: middle;" /> **GOVERN ITS ACTIONS**

Autonomy never makes the agent the authority. Tool calls pass through explicit permission modes, scoped rules, path restrictions, and human approval. Docker workspaces isolate execution, while the activity timeline records what ran, what changed, and why it was authorized.

### <img src="docs/assets/robot-gym.svg" width="28" style="vertical-align: middle;" /> **RUN IT ANYWHERE, LET IT WORK**

Goals, project tasks, subagents, Cron, and Heartbeat let the agent continue beyond one reply, inside isolated project workspaces and folders you already own—including an Obsidian vault—and across approved companion devices. Interactive turns checkpoint their session workspace before work begins, so retry restores both the conversation and local changes—not just the text.

Extend it further with portable `SKILL.md` packages and any MCP server you connect.

### <img src="docs/assets/robot-reader.svg" width="28" style="vertical-align: middle;" /> **KEEP ITS CONTINUITY**

GitHub Sync carries portable configuration, user skills, and Markdown memory through a private repository while credentials remain device-local. A provider can disappear, a model can change, and a machine can be replaced without taking the agent's continuity with it.

---

## **WHERE YOU TALK TO IT**

One agent, one memory, reachable from several surfaces. Messaging channels are off by default and access-controlled: a user ID must appear in `allowed_users` before the agent will answer it.

| Surface | Transport | Supports | Setup |
|---|---|---|---|
| **Desktop app** | Local backend | Full UI, Canvas, memory and skills browsers | `suzent start` |
| **Telegram** | Bot API | Text, photos, files | [Guide](docs/02-concepts/social-messaging/telegram.md) |
| **Slack** | Socket Mode (Events API) | Text, files | [Guide](docs/02-concepts/social-messaging/slack.md) |
| **Discord** | Gateway | Text, files | [Guide](docs/02-concepts/social-messaging/discord.md) |
| **Feishu (Lark)** | WebSocket | Text, files | [Guide](docs/02-concepts/social-messaging/feishu.md) |
| **WeChat** | iLink Bot API | Text | [Guide](docs/02-concepts/social-messaging/wechat.md) |

Each conversation becomes a persistent session, so history, working memory, and extracted facts survive a restart. Uploaded files land in the sandbox at `/persistence/uploads/`.

---

## **THE GRIMOIRE**

| Section | What's covered |
|---|---|
| [What is Suzent?](docs/01-getting-started/intro.md) | Core concepts and architecture overview |
| [Quickstart](docs/01-getting-started/quickstart.md) | Set up SUZENT from scratch in under 5 minutes |
| [Providers](docs/02-concepts/providers/README.md) | OpenAI, Anthropic, Gemini, Ollama, and more |
| [Memory](docs/02-concepts/memory/README.md) | How persistent memory works and how to configure it |
| [LLM Wiki](docs/02-concepts/memory/llm-wiki.md) | Agent-maintained structured knowledge vault |
| [Tools](docs/02-concepts/tools/tools.md) | Full reference for every built-in tool |
| [Canvas (A2UI)](docs/02-concepts/tools/canvas.md) | Interactive UI rendered in the sidebar |
| [Tool Approval](docs/02-concepts/tools/human-in-the-loop.md) | How dangerous tools require confirmation |
| [Skills](docs/02-concepts/skills/skills.md) | Extend the agent with portable knowledge modules |
| [Filesystem & Sandbox](docs/02-concepts/filesystem.md) | File access, sandboxed execution, storage paths |
| [Automation](docs/02-concepts/automation/automation.md) | Cron jobs and heartbeat monitoring |
| [GitHub Sync](docs/02-concepts/github-sync/README.md) | Carry portable brain data through a private repo |
| [Social Messaging](docs/02-concepts/social-messaging/README.md) | Telegram, Slack, Discord, Feishu, WeChat |
| [Nodes](docs/02-concepts/nodes/nodes.md) | Connect and control companion devices |
| [Retry](docs/02-concepts/runtime/retry.md) | Roll back the last agent turn and rerun it |
| [Development Guide](docs/03-developing/development-guide.md) | Setup, workflow, builds, architecture |

The full index lives in [docs/README.md](docs/README.md).

---

## **LORE**

SUZENT's docs and community speak in an occult register. There is a point behind the joke: the vocabulary of summoning and possession fits an agent you actually own far better than the vocabulary of seats, plans, and accounts. If you meet an unfamiliar word in these pages, it is probably here.

| Term | Means |
|---|---|
| **Summoning Ritual** | Installing and deploying SUZENT |
| **Incantation** | A prompt |
| **Summoner** | You—user, operator, developer |
| **Grimoire** | A skill the agent can learn, and the docs that teach it |
| **Soul Vessel** | The machine the agent runs on |
| **False God** | Cloud lock-in: the rented agent that forgets you when billing stops |
| **`{ ∅ }`** | The void—the local presence that keeps working when networks fail, dashboards burn, and rented memory evaporates |

---

## **TECH STACK**

*   **BACKEND**: Python 3.12, FastAPI, pydantic-ai, litellm, SQLite.
*   **FRONTEND**: React, TypeScript, Tailwind, Vite, Tauri.
*   **MEMORY**: LanceDB local vector storage.
*   **SANDBOX**: Docker.
*   **EXTENSIBILITY**: MCP, portable `SKILL.md` packages.

---

## **CONTRIBUTING**

Summoners welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow, and the [Development Guide](docs/03-developing/development-guide.md) for setup, production builds, and architecture.

---

## **SECURITY**

Found a vulnerability? Please report it privately—see [SECURITY.md](SECURITY.md). Do not open a public issue.

---

## **LICENSE**

**[APACHE 2.0](LICENSE)** © 2026 Yizhou Chi.

**Exception for Creative Assets:**
The creative assets, including the **Robot Avatar design**, **character animations**, and **project logos**, are subject to separate license terms. See [TERMS-OF-USE-ASSETS](TERMS-OF-USE-ASSETS.md) for details.

**SUMMON LOCALLY. REMEMBER PRIVATELY. ANSWER TO NO FALSE GOD.**
