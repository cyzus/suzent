
<div align="center">

![Suzent Banner](docs/assets/banner.svg)

# **SUZENT: YOUR SOVEREIGN DIGITAL CO-WORKER**
**[ LICENSE :: APACHE 2.0 ] • [ STATUS :: READY ] • [ SYSTEM :: AGENTIC ]**


**[QUICKSTART](docs/01-getting-started/quickstart.md)** • **[DOCS](docs/README.md)** • **[CONTRIBUTING](./CONTRIBUTING.md)**



</div>

---

## <img src="docs/assets/robot-idle.svg" width="30" style="vertical-align: middle;" /> **THE PHILOSOPHY**

> Your data. Your machine. Your rules.

SUZENT [soo-zuh-nt] combines SUZERAIN (sovereign) + AGENT (executor)—an automated system that answers to one authority: you. Built on the principles of digital sovereignty and open inspiration.


---

## **WHY SUZENT?**

SUZENT is an open-source deep research and co-worker agent that synthesizes ideas from leading AI products and projects—designed both as a fully functional tool you can use immediately and as inspiration for developers building their own agents. It demonstrates production-ready patterns for workspace management, local-first architecture, memory system, and agentic workflows, giving you a working reference implementation to learn from or extend.


## **FEATURES**

### <img src="docs/assets/robot-agnostic.svg" width="28" style="vertical-align: middle;" /> **MODEL AGNOSTIC**

**SUZENT** is model agnostic. It can use any model (GPT, Claude, Gemini, DeepSeek, etc.) you want.

### <img src="docs/assets/robot-gym.svg" width="28" style="vertical-align: middle;" /> **AGENTIC WORKFLOW**

**SUZENT** is a functionally rich agent that provides an experience comparable to OpenAI/Google Deep Research, Manus, and Claude Cowork — but fully open-source and locally runnable.

### <img src="docs/assets/robot-reader.svg" width="28" style="vertical-align: middle;" /> **TOOLS & SKILLS**

**SUZENT** provides simple but powerful tools for you to get started. It includes `bash`, `web search`, `web fetch`, and a series of file operations tools. These tools could guarantee you a competitive enough performance on GAIA benchmark.

You can create your custom tools and further connect to Google Drive, GitHub, or Slack via standard MCP protocol.

Agent skills are fully supported. Load your favorite skills to `./skills` folder to make **SUZENT** even more powerful.

### <img src="docs/assets/robot-peeker.svg" width="28" style="vertical-align: middle;" /> **WORKSPACE**

Unlike most agents, **SUZENT** features dual workspaces: a cross-session workspace shared across all chats for persistent knowledge, and per-session workspaces for individual conversations. This enables both continuity and isolation. You can also mount local folders (like your Obsidian vault) directly into the system.

### <img src="docs/assets/robot-thinking.svg" width="28" style="vertical-align: middle;" /> **MEMORY**

**SUZENT** implements a MemGPT-like global memory system that persists across sessions. This allows you to accumulate knowledge and context across conversations, making it easier to maintain a consistent and coherent conversation history.

### <img src="docs/assets/robot-snooze.svg" width="28" style="vertical-align: middle;" /> **PRIVATE & LOCAL**

**SUZENT** runs entirely on your device with built-in SearXNG for ad-free, tracking-free web search, PostgreSQL + pgvector for local vector storage, and MicroSandbox isolation for safe code execution. Your data never leaves your machine.

### <img src="docs/assets/robot-party.svg" width="28" style="vertical-align: middle;" /> **UI READY**

**SUZENT** features a NeoBrutalist web interface that transforms terminal-based agent interactions into a modern, aesthetically distinct experience—combining powerful functionality with bold visual design for your digital sovereign co-worker.

![SUZENT's NeoBrutalist Interface](docs/assets/new-chat.png)
*Clean, bold, and ready to work—your sovereign co-worker's command center.*

---

## **QUICK START**

### **THE "ONE-MINUTE" SETUP (DOCKER)**

```bash
# 1. CLONE YOUR NEW CO-WORKER
git clone https://github.com/cyzus/suzent.git
cd suzent

# 2. CONFIGURE (ADD KEYS)
cp .env.example .env
# Edit .env with your favorite API key

# 3. WAKE UP SUZENT
docker compose -f docker/docker-compose.yml up -d
```

▶ **OPEN: [LOCALHOST:5173](http://localhost:5173)**

---

## **TECH STACK**

*   **BACKEND**: Python 3.12, `smolagents`, `litellm`, Starlette, SQLite.
*   **FRONTEND**: React, TypeScript, Tailwind, Vite.
*   **MEMORY**: PostgreSQL + `pgvector`.
*   **SANDBOX**: MicroSandbox.

---

## <img src="docs/assets/robot-love.svg" width="30" style="vertical-align: middle;" /> **ACKNOWLEDGEMENTS**

SUZENT is built upon the collective intelligence and innovation of the open-source community. We are deeply grateful to the projects and contributors who make digital sovereignty possible.

---

## **LICENSE**

**[APACHE 2.0](LICENSE)** © 2026 Yizhou Chi.

**RECLAIM YOUR DIGITAL SOVEREIGNTY.**
