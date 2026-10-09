---
sidebar_position: 8
title: Devices & other agents
description: Pair your phone and other computers, let one Suzent drive another, delegate to A2A agents, and use Suzent from your editor.
---

# Devices & other agents

**Sovereign vessel.** Stretching an agent across devices is where most systems
quietly hand control to a cloud relay. Suzent connects only the devices you
pair, over links you approve, with each device declaring what it can do. See
[what makes an agent sovereign](https://suzent.com/sovereign).

Suzent can reach beyond the computer it runs on:

- **Your phone** can chat with your agent through the Suzent app.
- **Other devices** (laptops, servers, phones, even a TV browser) can lend the
  agent their hardware, such as a camera or speaker.
- **Another Suzent** on a different computer can be asked to do work with its
  own files and memory.
- **Other agents** that speak the open A2A standard can take on delegated work.
- **Your code editor** can use Suzent as its agent through ACP.

Everything here is managed in **Settings → Devices** and **Settings → Mesh**.

## Step 1: Make this computer reachable

Out of the box, Suzent only listens to your own computer, so other devices
can't reach it. To change that, open **Settings → Mesh → Network access**, turn
it on, and restart Suzent. Your other devices can then find it on your home
network or your [Tailscale](https://tailscale.com/) network.

Being reachable doesn't open anything up by itself: every device still has to
be approved by you, and an approved device can only do what you granted.

:::warning
Only do this on a network you trust, such as your home Wi-Fi or Tailscale.
Letting another device drive your agent is close to letting it run code on
your computer.
:::

## Pair your phone

The Suzent app for Android and iOS pairs from **Settings → Devices → Mobile
access**, with its own permissions for each phone. See
[Mobile app](./mobile.md).

A phone that may send messages can also attach things to them: tap **+** next
to the message box to take a photo or video, pick from your photo library, or
choose a file. Attachments are saved in the conversation's workspace on your
computer, under `uploads/`, never on a cloud service. Up to 10 items go with one
message. If the model reads images, it sees photos directly; videos and other
files are handed to the agent to open with its tools.

## Connect another device

Open **Settings → Devices → Discover**. Suzent lists devices on your local
network and your Tailscale network.

- **To use a device's hardware**, click **Connect** on it. A pairing code
  appears, and whoever owns that device approves it in their **Settings →
  Devices**.
- **To add a phone, tablet, or TV without installing anything**, use **Add a
  screen (phone, tablet, TV)** and scan the QR code with that device's camera.
- **To connect a headless server**, run this on the server, then approve the
  pairing code on your main computer:

  ```bash
  suzent nodes host --name "My Server"
  ```

Approval is a one-time step. The device remembers its access and reconnects on
its own until you revoke it.

Once connected, just ask: "take a photo with my phone", or "play this on the
living-room speaker". You can see each device's abilities in the device list.

## Drive another Suzent

If both computers run Suzent, one can ask the other's agent to do work using
that computer's own files, memory, and tools.

1. On the computer that will give the orders, open **Settings → Devices →
   Discover** and click **Control** on the other one.
2. On the other computer, approve the request in **Settings → Devices**.
3. Now ask your agent, for example, "ask my desktop to summarize ~/notes". The
   other computer's reply streams back, and the conversation appears in its
   chat list too.

From the command line, with files attached:

```bash
suzent nodes trigger "Desktop" "summarize these" --file ./notes.txt
```

A control grant lets the other computer run its agent for you, and nothing
else: it can't read your settings or files directly. Each link has two
independent directions, so "I can control them" and "they can control me" are
granted and revoked separately. Pause or remove a link at any time in the
device list.

To operate a computer fully from elsewhere, create a host token in **Settings →
Security**. It grants complete access, is
shown only once, and can be revoked like any device. Treat it like a password.

## Work with other agents (A2A)

[A2A](https://a2a-protocol.org/) is an open standard that lets agents built by
different people delegate work to each other.

- **To delegate to an external agent,** add its address under **Settings →
  Mesh → Agents in your mesh**. Your agent can then hand it tasks, and you can
  follow them under **Delegated work**.
- **To let other agents find this device,** turn on **This device** in
  **Settings → Mesh**. That publishes a card describing your agent. Publishing
  is off by default, and it grants nothing: another agent still needs a grant
  you approve before it can send work. Work sent to you appears under **Work
  given to you**.

## Use Suzent from your editor (ACP)

Editors and tools that support the
[Agent Client Protocol](https://agentclientprotocol.com/), such as Zed, can use
Suzent as their AI agent. Each session is a real Suzent conversation, with your
memory, skills, models, and permission rules, and it shows up in the desktop
app too.

1. Keep Suzent running (`suzent start`, or the
   [background service](./automation.md#keep-suzent-running-in-the-background)).
2. In your editor's settings for external agents, add a custom agent with the
   command `suzent` and the argument `acp`.

The editor's open folder becomes the agent's working folder. When the agent
needs permission, the editor asks you. To skip those prompts for unattended
use, add `--permission-mode auto` or `--permission-mode full_access` to the
arguments.

It also works the other way around: under **Settings → ACP Agents**, Suzent can
use coding agents such as Claude Code or Codex as helpers.

## Command line reference

```bash
suzent nodes discover               # find devices on your network and Tailscale
suzent nodes list                   # connected devices
suzent nodes describe <name>        # what a device can do
suzent nodes pending                # pairing codes waiting for approval
suzent nodes approve <code>
suzent nodes devices                # approved devices
suzent nodes revoke <device_id>     # remove a device; it must pair again
```
