---
sidebar_position: 7
title: Mobile app
description: Use your agent from your phone with the Suzent app for Android and iOS, what it can do, and how to pair and unpair it.
---

# Mobile app

The Suzent app for Android and iOS is a remote control for the agent on your
computer. Your memory, files, and keys stay on that computer: the phone only
shows your conversations and sends your messages, under permissions you choose
for each phone.

:::note
The mobile app is a preview. It works, but it isn't in the App Store or Google
Play yet, and some desktop features are missing (see [Limits](#limits)).
:::

## Get the app

| | Requirement | Where to get it |
|---|---|---|
| **Android** | Android 8 or later | Download the APK from a `mobile-v...` release on [GitHub Releases](https://github.com/cyzus/suzent/releases) and install it. |
| **iOS** | iOS 17 or later | Distributed through TestFlight. |

## Pair your phone

1. **Make your computer reachable.** Open **Settings → Mesh → Network access**,
   turn it on, and restart Suzent. See
   [Make this computer reachable](./nodes.md#step-1-make-this-computer-reachable).
2. **Choose what the phone may do.** Open **Settings → Devices → Mobile access**.
   **Restrict access** lists the permissions:

   | Permission | Lets the phone |
   |---|---|
   | **Read all conversations, including future ones** | See every chat. Untick it to pick chats one by one under **Conversations this phone can read**. |
   | **Create conversations** | Start new chats. |
   | **Manage conversations (pin, rename, move, delete)** | Organize chats. Off by default. |
   | **Send messages** | Write to the agent, which can then use its tools under the chat's usual [permission mode](./tools/human-in-the-loop.md). |
   | **Stop responses** | Stop a reply in progress. |
   | **Approve tool requests** | Answer the agent's approval requests. |

3. **Check the address.** **Backend address reachable from your phone** is
   filled in for your home network. Connections on your home network are
   encrypted automatically; you don't need a certificate.
4. **Click Pair a phone.** In the app, tap **Scan desktop QR code** (or
   **Paste an invitation instead** after **Copy pairing invitation** on the
   computer), check the permissions it shows, and tap **Confirm connection**.
   You don't need to approve anything again on the computer.

The QR code works once and expires after a few minutes. Anyone who scans it
gets the permissions you picked, so don't share it.

### Using it away from home

The phone talks to your computer directly; there's no Suzent cloud in between.
On your home Wi-Fi that just works. To use it elsewhere, put both devices on
[Tailscale](https://tailscale.com/), or give Suzent a public HTTPS address of
your own. Your computer has to be on and running Suzent; the
[background service](./automation.md#keep-suzent-running-in-the-background)
keeps it running when the window is closed.

## What you can do on the phone

- **Chats.** Browse your conversations grouped by project, search them, see
  pinned ones first, and start a new one in any project.
- **Talk to the agent.** Send messages, watch replies stream in with their
  sources, stop a reply, edit and resend your last message, retry a reply, or
  branch a conversation.
- **Pick the model.** **Desktop model** lists the models you've enabled on
  your computer.
- **Answer approvals.** When the agent needs permission, the app shows
  **Approval required** with **Allow once** and **Reject** for each request.
- **Organize.** Long-press a chat to pin, rename, move, or delete it, if the
  phone may manage conversations.

The app is in English and Simplified Chinese. If the connection drops, it
reconnects when you open it again and picks up a reply where it left off.

## Change or remove access

On your computer, each paired phone is listed under **Mobile access** with its
permissions. You can switch **Manage conversations (pin, rename, move, delete)** on or off
there; to change
any other permission, tap **Pair again** in the app and pair with new
permissions. **Revoke access** cuts the phone off immediately: the next time
it connects, it signs out and asks you to pair again.

**Forget connection** in the app only removes the connection from the phone.
Also click **Revoke access** on the computer so its access is gone too.

## Limits

The preview doesn't yet have:

- notifications, so the phone stays quiet until you open the app;
- attachments, voice input, or the agent's interactive forms and buttons;
- memory, settings, or tool permissions, which stay on the computer;
- offline access to your conversations.

For the technical design, see the
[mobile architecture](../08-developing/architecture/mobile.md).
