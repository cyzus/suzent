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
| **Android** | Android 8 or later | Download the [latest APK](https://suzent.com/download/android/) and install it. Earlier versions are on [GitHub Releases](https://github.com/cyzus/suzent/releases) under `mobile-v...`. |
| **iOS** | iOS 17 or later | Join the [TestFlight beta](https://suzent.com/download/ios/): install Apple's TestFlight app, open the invitation, and accept it to install Suzent. Places depend on an approved build and room in the test group. |

## Try it without a computer

Tap **Try offline demo** at the bottom of the app's connection screen to look
around with sample data. On a paired phone it's under **Settings → About**. You
don't need a computer, an API key, or an internet connection: you can send
messages, try a trip-planning example, approve or reject a pretend tool request,
attach files, and organize chats.

Replies are scripted and nothing reaches an AI model; a banner says so the whole
time. Attachments stay on the phone. **Reset demo** in Settings restores the
examples, and **Exit demo** takes you back to the connection screen. An existing
pairing is kept while you're in the demo.

## Pair your phone

1. **Make your computer reachable.** Open **Settings → Mesh → Network access**,
   turn it on, and restart Suzent. See
   [Make this computer reachable](./nodes.md#step-1-make-this-computer-reachable).
2. **Choose what the phone may do.** Open **Settings → Devices → Mobile access**
   and expand **Phone permissions**. Pick one of these; **Full control** is
   selected for you:

   | Choice | Lets the phone |
   |---|---|
   | **Full control** | Do everything you can do in a chat on the computer: read and organize every conversation, chat with the agent, and answer its approval requests. Best for your own phone. |
   | **Chat only** | Read every conversation and chat with the agent, but not answer approval requests or rename, move, or delete chats. |
   | **Read only** | See every conversation without sending anything. |
   | **Custom** | Choose each permission yourself, and pick which conversations the phone can read. |

   With **Custom**, the permissions are:

   | Permission | Lets the phone |
   |---|---|
   | **Read all conversations, including future ones** | See every chat. Untick it to pick chats one by one under **Conversations this phone can read**. |
   | **Create conversations** | Start new chats, and branch a conversation. |
   | **Manage conversations (pin, rename, move, delete)** | Organize chats, and, together with **Send messages**, edit and resend or retry a reply. |
   | **Send messages** | Write to the agent, which can then use its tools under the chat's usual [permission mode](./tools/human-in-the-loop.md). |
   | **Stop responses** | Stop a reply in progress. |
   | **Approve tool requests** | Answer the agent's approval requests. |

   Whatever you pick, the agent's tools still follow each chat's permission
   mode, and you can change or revoke the phone's access at any time.

3. **Check the address.** Under **Connection settings**, **Backend address
   reachable from your phone** is filled in for your home network. Connections on your home network are
   encrypted automatically; you don't need a certificate.
4. **Click Pair a phone.** In the app, tap **Scan desktop QR code** (or
   **Paste an invitation instead** after **Copy invitation** on the
   computer), check the permissions it shows, and tap **Confirm connection**.
   You don't need to approve anything again on the computer.

The QR code works once and expires after a few minutes; click **New QR code**
for another. Anyone who scans it gets the permissions you picked, so don't
share it.

### Using it away from home

The phone talks to your computer directly; there's no Suzent cloud in between.
On your home Wi-Fi that just works. To use it elsewhere, put both devices on
[Tailscale](https://tailscale.com/), or give Suzent a public HTTPS address of
your own. Your computer has to be on and running Suzent; the
[background service](./automation.md#keep-suzent-running-in-the-background)
keeps it running when the window is closed.

## What you can do on the phone

- **Find a chat.** The app opens on your conversations. **SUZENT Regent** and
  **New conversation** are at the top, then pinned chats, your three most
  recent with **View all**, your projects (tap one to open it, and **Load
  more** for older chats), and your scheduled tasks. Search looks through the
  titles of every chat the phone may read, not only the ones already loaded.
  **Settings** is in the top toolbar.
- **Talk to the agent.** Send messages, watch replies stream in with their
  sources and an activity summary you can expand for each tool's details, and
  stop a reply. Long-press a message to copy or share it, edit and resend your
  last message, retry a reply, or branch a conversation. Edit and retry need
  **Full control** (or the manage permission under **Custom**).
- **Talk to Regent.** If the phone may read all conversations, you can talk to
  [Suzent Regent](../02-using/regent.md) as on the computer, see when it's
  working or needs you, and open the conversations it handed work to. You
  can't attach files, edit, retry, or branch in Regent's chat from the phone.
- **Attach things.** Tap **+** next to the message box and choose **Camera**,
  **Photos and videos**, or **Files**. Up to 10 items go with one message, up
  to 200 MB in all. They're saved in the conversation's workspace on your
  computer, under `uploads/`. If the model reads images, it sees photos
  directly; other files are handed to the agent to open with its tools.
  Attaching needs the **Send messages** permission.
- **Pick the model.** **Desktop model** lists the models you've enabled on
  your computer.
- **Answer approvals.** When the agent needs permission, **Approval required**
  appears above the message box with **Allow once** and **Reject** for each
  request.
- **Organize.** Long-press a chat to pin, rename, move, or delete it, or swipe
  it to pin or delete, if the phone has **Full control** (or may manage
  conversations).
- **Follow background work.** Sub-agent chats fold under the chat that
  started them. **Scheduled tasks** shows failed tasks first, then active and
  paused ones, with their status and next run. You can open a task's chat but
  not change the task from the phone.

The app is in English and Simplified Chinese, and follows your phone's light
or dark mode. If the connection drops, it reconnects when you open it again and
picks up a reply where it left off. If it can't, **Connection help** has
**Pair again** and **Forget connection**.

## Change or remove access

On your computer, **Paired phones** under **Mobile access** lists each phone
by name with what it may do. Click **Edit permissions**, pick another choice
(or **Custom**), and **Save**; the phone keeps working with the new permissions straight away.
**Revoke access** cuts the phone off immediately: the next time it connects, it
signs out and asks you to pair again.

**Forget connection** in the app only removes the connection from the phone.
Also click **Revoke access** on the computer so its access is gone too.

## Limits

The preview doesn't yet have:

- notifications, so the phone stays quiet until you open the app;
- voice input, or the agent's interactive forms and buttons;
- memory, settings, or tool permissions, which stay on the computer;
- offline access to your conversations.

For the technical design, see the
[mobile architecture](../08-developing/architecture/mobile.md).
