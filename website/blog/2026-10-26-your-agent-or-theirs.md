---
slug: your-agent-or-theirs
title: "Your Agent, or Theirs?"
description: "Personal agents went mainstream in 2026. Six big vendors now sell an always-on assistant that knows you increasingly well. Here is the quiet trade at the center of every one of them — and the question only you can answer."
authors: [suzent]
tags: [sovereignty, personal-agent, data-sovereignty]
date: 2026-10-26T09:00:00
---

Somewhere in the last year, "personal AI agent" stopped being a category in a
pitch deck and became a thing normal people are told they should want. In 2026
it is not one product but a whole shelf of them, each promising the same thing
with different branding: an assistant that knows you, that works while you
sleep, that handles your email and your calendar and — soon, they all say, in
the next update — the boring parts of your life.

The pitch is seductive because it is close to something real. An agent that
actually knows you is genuinely more useful than one that does not. That is not
marketing; it is how context works. The question is what that usefulness is
built on, and who it ultimately serves.

This post is not another "big tech is evil" list. Every product below solves a
real problem for real people. But every one of them also sits on the same
unspoken architecture, and it is worth understanding that architecture before
you hand it the contents of your life.

<!-- truncate -->

## First, what a personal agent actually is

The word has been stretched until it barely means anything, so a short taxonomy
helps.

- **A chatbot** answers what you ask, then forgets. No memory, no initiative.
- **A copilot** assists inside a specific context — an editor, a spreadsheet —
  and disappears when you leave.
- **An agent** has *memory* (it remembers), *authority* (it acts — runs tools,
  sends things, changes state), and *continuity* (it keeps running without you
  standing over it).
- **A personal agent** is the agent aimed at *you* rather than at a business
  workflow: your inbox, your calendar, your files, your life. It is the
  difference between a tool you point at a task and a system you point at your
  week.

The defining property is not intelligence. It is **persistence plus
authority**. An agent that cannot act is a chatbot with better recall. An agent
that cannot remember is a script. The entire 2026 crop is betting that the
combination — persistent *and* trusted to act — is the next platform.

## The 2026 lineup

Here is who is selling you an agent this year, in rough order of when they
showed up.

| Vendor | Product | Announced | What it runs on | The pitch |
|---|---|---|---|---|
| **Anthropic** | Claude Cowork | Feb 2026 | Cloud | Automates business workflows; the launch wiped roughly $285B off SaaS, IT, and legal market caps |
| **Apple** | Siri (Apple Intelligence) | 2026 | On-device-first | The private upgrade: your iPhone does it locally |
| **Microsoft** | Copilot | 2026 | Cloud | A "three-horizon AI architecture" rebuilt across Windows and Microsoft 365 |
| **Meta** | Muse | Sep 8, 2026 | Cloud | The most-downloaded app on arrival; performs tasks on your behalf and expanded to small-business agents within weeks |
| **OpenAI** | Dots | Sep 29, 2026 (DevDay) | Cloud (GPT-6 Astra) | Always-on personal agents with avatars, working across ChatGPT, Slack, and Teams |
| **Google** | Gemini Spark | I/O 2026 | Cloud (Gemini 3.5 Flash + Antigravity) | A 24/7 agent that drafts email, watches your inbox, files things, pulls PDF data into Sheets — and, they say, will eventually spend your money |

Two patterns jump out. First, **the timeline is accelerating**: what the
enterprise world took a couple of years to adopt, the personal-agent market
compressed into about nine months. Second, **the direction of every pitch is
identical.** The more of your data the agent can touch, the more "useful" it is
described as being. That is the load-bearing fact, and every vendor says it
like it is a feature rather than a dependency.

<img src="/img/personal-agent-lineup.svg" width="800" height="455" alt="The 2026 personal-agent lineup across six vendors: Anthropic Claude Cowork, Apple Siri Intelligence, Microsoft Copilot, Meta Muse, OpenAI Dots, and Google Gemini Spark." />

## "Your agent" — a short translation guide

Each word in the marketing does real work. It is worth knowing what it is
doing.

| You hear | Which means | What it does not say |
|---|---|---|
| **"Your agent"** | The account remembers you, in the vendor's database | *You* do not own the thing that remembers |
| **"Memory"** | A vector store on their servers, tuned to serve you better | Readable, portable, editable? No such claim is made |
| **"Works for you"** | Executes inside their sandbox, through their integrations | Whose rules define the limits? Their terms of service |
| **"Private"** | Encrypted at rest and in transit, with the operator able to read it as needed | "Private from other users" is not the same as "private from the operator" |
| **"On-device"** (Apple) | Inference runs locally on your hardware | The memory and identity still sync back into the account by default |

None of this is a lie. That is the tricky part. "Private" and "memory" and
"works for you" are all true in the sense the vendor means them. The
misdirection is in what the sentences *leave out* — specifically, who can read,
move, edit, and survive the thing that knows you.

## The real question: integration versus sovereignty

Every honest framing of this market keeps coming back to the same fork:

> **Are you willing to integrate all of your data more tightly into one
> company — or do you keep it for yourself?**

This is not abstract. Everything the agent does well — deduplicating your
inbox, anticipating your schedule, filing your receipts — is powered by
*integration*: the more of your life flows into one graph, the smarter the
agent becomes about you. Integration is genuinely what makes these products
feel magical. That is the honest case for the big-vendor agent, and it is a
good one.

The honest case for the other side is that **integration and ownership sit on
the same axis, and they point in opposite directions.** Every degree you deepen
the integration, you deepen your dependence on whoever holds the graph. The
agent that knows you best is, by construction, the one you can least afford to
lose — and the one with the most complete picture of you.

You cannot optimize for both at full throttle. You can have a maximally helpful
agent, or a maximally yours agent, and you have to choose how far to lean. What
sovereignty offers is not more convenience — it is **the option to say no,
without having to start over.**

<img src="/img/personal-agent-anatomy.svg" width="800" height="455" alt="Anatomy of a personal agent: Identity, Memory, Authority, Continuity, and Permissions form the vehicle you own, while the model underneath is a swappable engine." />

<img src="/img/personal-agent-data-routes.svg" width="800" height="418" alt="Comparison of data flows: the Integration Route funnels your life into one vendor's cloud graph and rents access back to you; the Sovereign Route keeps your data, memory, and permissions on your machine." />

## There is a sane middle path

This does not have to be a clean either/or, and pretending otherwise is its own
kind of dishonesty. The useful distinction is between **the engine and the
vehicle**.

- **The engine** is the model — the intelligence. That can be rented. Frontier
  models are genuinely, measurably better at many things, and there is no shame
  in using them.
- **The vehicle** is your agent — its memory, its skills, the rules of what it
  may do, its identity, where it lives. That is what should be *yours*.

A sovereign agent that calls GPT, Claude, or Gemini through an API keeps
cutting-edge capability while holding memory, permissions, and identity on
*your* side of the line. You rent the engine; you own the vehicle. That
configuration is what most people actually want, and it is what Suzent is built
to be: [memory as files you own](https://suzent.com/docs/features/memory), [any
model you choose](https://suzent.com/docs/models), and [explicit permission
rules with human approval gates](https://suzent.com/docs/features/tools/human-in-the-loop).

## Four questions to ask before you hand one over

Whatever you pick, these cut through the copy. If you cannot answer them, you do
not yet know what you are buying.

1. **Can I read all of its memory** — in a plain format I can open? Not a
   settings preview. The whole thing.
2. **Can I edit or delete what it believes about me?** Or is my only recourse
   telling it nicely and hoping the correction sticks?
3. **Can I disable, approve, and audit what it is allowed to do?** Or is "what
   it may do" a sentence in a terms-of-service I accepted once?
4. **If the vendor disappears, shuts down, or triples the price — does my agent
   survive?** Or was the agent actually a rental dressed as a companion?

A personal agent is going to become the most intimate software you own — more
so than your email, your browser, maybe your phone. It will know what you
decided, what you abandoned, what you are afraid to admit you keep putting off.
The only question that ever really mattered, and the one this post keeps
circling, is the one you should sit with before you click past the next
changelog:

**Are you willing to integrate it — all of it, more tightly every year — into
one company? Or do you keep it for yourself?**

---

[Quickstart](https://suzent.com/docs/getting-started/quickstart) ·
[Source](https://github.com/cyzus/suzent) (Apache-2.0)
