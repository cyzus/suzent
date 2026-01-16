# Suzent Quickstart Guide

This guide will help you set up Suzent from scratch, even if you're new to development tools.

---

## 1. Get an API Key

Suzent needs an "brain" to work. You need an API key from one of these providers:

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

## 2. Set Up the Project

### Windows
1. Install **Docker Desktop**: [Download here](https://www.docker.com/products/docker-desktop/)
2. Install **Git**: [Download here](https://git-scm.com/download/win)
3. Open **PowerShell** and run:

```powershell
# Clone the project
git clone https://github.com/cyzus/suzent.git
cd suzent

# Create configuration file
Copy-Item .env.example .env

# Open .env in Notepad (or your favorite editor)
notepad .env
```
4. Paste your API key into the `.env` file:
```env
OPENAI_API_KEY=sk-your-key-here
# or
GEMINI_API_KEY=your-key-here
```
5. Save and close the file.

### Mac / Linux
# Clone the project
```bash
git clone https://github.com/cyzus/suzent.git
cd suzent

# Configure environment
cp .env.example .env
nano .env
```
3. Paste your API key, save (Ctrl+O), and exit (Ctrl+X).

---

## 3. Run Suzent

In your terminal (PowerShell or Terminal), run:

```bash
docker compose -f docker/docker-compose.yml up -d
```

- This downloads necessary parts (images) and starts them. 
- It might take a few minutes the first time.
- If successful, you'll see "Started" next to `suzent-frontend`, `suzent-backend`, etc.

---

## 4. Start Chatting

1. Open your browser to [**http://localhost:5173**](http://localhost:5173).
2. You should see the chat interface.
3. Type "Hello!" to test it out.
4. Try a search: "Search for the latest news on AI agents."

---

## Troubleshooting

### "Docker is not running"
Make sure you started the **Docker Desktop** application and verified the whale icon is in your taskbar/menu bar.

### "Connection refused"
Wait a minute. Sometimes the backend takes a moment to start up completely. Refresh the page.

### Memory/Search not working?
Check the logs to see if a service failed:
```bash
docker compose -f docker/docker-compose.yml logs
```

### Developing Suzent?
If you want to modify the code, use **Dev Mode** which only runs the database and search engine in Docker, letting you run the app locally:
```bash
# Start infra only
docker compose -f docker/docker-compose.dev.yml up -d

# Run app locally
python src/suzent/server.py
npm run dev
```
