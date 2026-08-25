---
slug: when-your-ai-provider-disappears
title: "What Happens to Your AI Agent When the Provider Shuts Down"
description: "Model deprecations, price changes, and product sunsets are routine. What you actually lose depends entirely on which side of the boundary your agent's memory and configuration live."
authors: [suzent]
tags: [sovereignty, continuity, sovereign-ai]
date: 2026-08-25T12:00:00
---

Shutdowns make the argument vividly, but they are the rare case. The common case
is quieter and happens constantly: a model you depended on is deprecated, a
price tier changes, a product is folded into another product, a rate limit
arrives, terms are revised, a feature you built a workflow around is retired.

The interesting question is not whether that happens. It is what it costs you
when it does — and that is decided long before, by where your agent's durable
parts live.

{/* truncate */}

## Two versions of the same bad Tuesday

Suppose the provider behind your agent announces a sunset in ninety days.

**If your agent is an account**, the ninety days are a migration project. The
accumulated context — everything it learned about your work — is in a database
you can query only through whatever export the vendor offers, in whatever shape
they offer it. Custom instructions have to be rewritten for a different product
with different conventions. Integrations have to be rebuilt against different
APIs. And the new agent starts at zero: it does not know your projects, your
preferences, or the eleven things you already told the old one not to do.

The cost is not the subscription. It is the re-accumulation.

**If your agent is a system you own**, the ninety days are a config edit. The
memory is Markdown in a directory you control, unchanged. The skills are your
own Markdown modules, unchanged. The permission rules are yours, unchanged. You
point at a different provider, and the agent that knows your work continues
knowing it.

What you lost was an API key.

## The boundary that decides which Tuesday you get

The distinction is not paranoia about vendors and it is not a bet on which
company survives. It is a structural question you can answer in advance:

> Which parts of this agent could the provider take away, and which parts are
> already mine?

For a sovereign AI agent, the answer is drawn deliberately:

- **Memory** — [Markdown files on your disk](https://suzent.com/docs/concepts/memory),
  readable and versionable.
- **Skills** — knowledge modules you author, in your own directory.
- **Configuration and permissions** — rules you wrote, stored locally.
- **Workspace** — [folders and sandboxes you granted](https://suzent.com/docs/concepts/filesystem).
- **The model** — rented, deliberately, and replaceable.

Everything above the last line is yours regardless of what happens to the
company below it. That is what the fifth question of the
[sovereignty test](https://suzent.com/sovereign) is checking: *can the agent
survive the disappearance of its provider?*

## Continuity is a design decision, not a promise

It is worth being precise about what makes this work, because "we will never
shut down" is not a plan and no vendor can honestly offer one.

Continuity comes from two properties, both of which are architectural:

**Identity is not in the model.** If what makes the agent *yours* is its
memory, skills, and workspace rather than a specific set of weights or a
specific vendor's fine-tune, then models become interchangeable engines. Suzent
supports [many providers](https://suzent.com/docs/concepts/providers) and lets
you switch per session precisely so that no single one becomes load-bearing.

**State is portable without secrets.** Moving an agent should not mean moving
your credentials. Suzent's
[sync design](https://suzent.com/docs/concepts/github-sync) carries
configuration, skills, and Markdown memory to a private repository while keeping
API keys, device identity, and the local secret store off the wire entirely.

Neither of these is exotic. Both have to be decided early, because retrofitting
portability onto an agent whose memory is a proprietary blob is not a small
change — it is a rewrite.

## The unglamorous version of the advice

You do not need to predict which provider will falter. You need your agent's
answer to one question to be yes:

If this provider vanished tonight, would I still have the agent tomorrow?

Keep the memory in files you can open. Keep the permissions in rules you wrote.
Keep the credentials separable from both. Then a sunset notice is an
inconvenience rather than an eviction.

---

[Read the sovereignty protocol](https://suzent.com/sovereign) ·
[Quickstart](https://suzent.com/docs/getting-started/quickstart) ·
[Source](https://github.com/cyzus/suzent)
