# Suzent Quickstart Guide

This guide will help you set up Suzent, your sovereign digital co-worker.

---

## 1. Get an API Key

Suzent is model-agnostic but needs a "brain" to work. You need an API key from one of these providers:

### OpenAI (ChatGPT)
1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign up or log in
3. Go to **API Keys** and create a new secret key
4. Copy the key (starts with `sk-...`)

### Anthropic (Claude)
1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign up or log in
3. Click **Get API Keys** and create a key
4. Copy the key (starts with `sk-ant-...`)

### Google (Gemini) - **Free Tier Available**
1. Go to [aistudio.google.com](https://aistudio.google.com/app/apikey)
2. Create an API key
3. Copy the key

---

## 2. Installation (Native Setup)

The recommended way to run Suzent is natively on your machine using our setup script.

**Prerequisites:**
- **Node.js 20+**: [Download here](https://nodejs.org/)
- **Git**: [Download here](https://git-scm.com/downloads)

### Fast Install

Run the following command in your terminal to install `suzent` and its dependencies (UV, Rust, etc.):

**Windows (PowerShell):**
```powershell
powershell -c "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

**Mac / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

> **Note:** The setup script will attempt to install `uv` (Python package manager) and `Rust` (for core performance) if they are missing. On Windows, it may also install C++ Build Tools if needed.

---

## 3. Configure Your Agent

1. The setup script created a `.env` file in the project directory.
2. Open this file in any text editor.
3. Paste your API Key from **Step 1**:

```env
OPENAI_API_KEY=sk-your-key-here
# or
GEMINI_API_KEY=your-key-here
```

4. Save and close the file.

---

## 4. Launch Suzent

To start your agent, simply run:

```bash
suzent start
```

This will:
- Check system health.
- Start the Backend (Brain) on port `25314`.
- Start the Frontend (UI) on port `5173`.
- Automatically manage local processes.

**Start Chatting:** Open your browser to [**http://localhost:5173**](http://localhost:5173).

---

## Troubleshooting

### "Command not found: suzent"
Restart your terminal after installation to refresh your `PATH`. If it still fails, check the output of the setup script for manually adding the scripts folder to your PATH.

### "System Health Check Failed"
Run the doctor command to identify missing tools:
```bash
suzent doctor
```

### Port Conflicts
If Suzent fails to start because ports are in use, `suzent start` will ask if you want to kill the conflicting processes. You can say 'y' to proceed.

### Updating Suzent
To get the latest features and fixes:
```bash
suzent upgrade
```

---

## Advanced

### Local Web Search (Privacy Focused)
By default, Suzent uses DuckDuckGo for search (no setup required). To use a private, self-hosted search engine (SearXNG), you can use Docker.

See: [Docker Services](../03-developing/docker-services.md)
