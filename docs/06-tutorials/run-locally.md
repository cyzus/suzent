---
sidebar_position: 1
title: Run everything on your own computer
description: Use Ollama so your conversations never leave your machine, with no API key and no account.
---

# Run everything on your own computer

**Sovereign mind.** The most private agent is one whose model runs on your own
hardware. With [Ollama](../04-models/local/ollama.md), nothing you say leaves
your computer, and nothing depends on an account someone else can close.

You'll need a computer with enough memory for the model you choose. Small
models (3B to 8B parameters) run on most laptops; larger ones want a GPU.

## 1. Install Ollama and pull a model

Install Ollama from [ollama.com](https://ollama.com), then pull a model that
supports tool calling, which the agent needs to act:

```bash
ollama pull llama3.2
```

## 2. Connect it to Suzent

1. Open **Settings → Providers → Ollama** and click **FETCH**.
2. Tick the model you pulled and click **Save Changes**.

## 3. Use it for everything

Open **Settings → Model Roles** and set **Primary** to your Ollama model.
Leave **Cheap** empty, and it will use the same model; or pull a smaller one
for background jobs and assign it to **Cheap**. See
[Model roles](../04-models/model-roles.md).

Memory search needs an embedding model. To keep that local too, pull one:

```bash
ollama pull nomic-embed-text
```

Add `ollama/nomic-embed-text` under **Custom Models** on the Ollama card, then
assign it to the **Embedding** role. If you leave **Embedding** empty, Suzent
still remembers facts about you, but memory search is turned off.

## 4. Mind the tools that reach the internet

The model is now local, but some tools still go online when the agent uses
them, such as web search and the browser. If you want the agent fully offline,
turn the **Web** group off in the chat's tool selector (see
[Tools](../03-features/tools/README.md)).

## Check it worked

Start a new chat, pick your Ollama model in the model selector, and ask
something. If answers are slow, try a smaller model; if the agent never uses
tools, try a model with stronger tool support.
