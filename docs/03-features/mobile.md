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
| **iPhone and iPad** | iOS 17 or later | Join the [TestFlight beta](https://suzent.com/download/ios/): install Apple's TestFlight app, open the invitation, and accept it to install Suzent. Places depend on an approved build and room in the test group. |

The app's [privacy policy](https://suzent.com/mobile-privacy) is also linked
from the connection screen and from **Settings → About**.

## Try it without a computer

Tap **Try offline demo** at the bottom of the app's connection screen to look
around with sample data. On a paired phone it's under **Settings → About**. You
don't need a computer, an API key, or an internet connection: you can send
messages, try a trip-planning example, approve or reject a pretend tool request,
attach files, and organize chats.

Replies are scripted and nothing reaches an AI model; the pinned **Welcome to
Suzent** conversation explains this. Attachments stay on the phone. **Reset demo** in Settings restores the
examples, and **Exit demo** takes you back to the connection screen. An existing
pairing is kept while you're in the demo.

## Talk with Suzent

In a conversation, leave the message box empty and tap the waveform button to
start a voice conversation. Allow microphone access when prompted. The input
area shows the same animated cube as desktop, together with call status and live
captions. The cube responds to your microphone and to Suzent listening, thinking,
and speaking. Tap the hang-up button to end the call.
During a call, the action stays **Hang up** (or **Cancel** while connecting).
Outside a call, typing a message or attaching a file switches the waveform button
to **Send**, and a running agent task shows **Stop**. A progress indicator
replaces the action while a message is being processed. If voice needs setup or
additional permissions, tapping its button explains what to change.

### Redirect or queue while the agent works

You don't have to wait for a reply to finish. Type while the agent is working and
the **Stop** button gives way to two buttons:

- **Redirect** (yellow arrow) interrupts the agent and continues the same turn
  with your new message, like pressing Enter mid-reply on desktop. What the agent
  had written so far stays in the conversation.
- **Queue** (clock) holds the message until the current reply ends, then sends it
  as the next message, like Cmd/Ctrl+Enter on desktop.

Queued messages appear above the message box. Tap **Redirect now** on one to send
it straight away, or the ✕ to drop it. Queued messages go out in order while the
conversation is open, and they are kept only on the phone until then. If one
can't be sent, it returns to the message box so nothing you typed is lost.
Redirect needs both **Send messages** and **Stop responses**; with only **Send
messages**, or with attachments alone, you can still queue. Redirect sends text
only, so any attachments stay in the message box.

Use a desktop version that supports mobile voice and configure a realtime voice
model in **Settings → Voice & audio** on the desktop first. Your phone needs both **Send
messages** and **Stop responses** permissions, because voice can start and cancel
agent tasks. Starting a call in a new conversation also requires **Create
conversations**. Voice is unavailable in the offline demo.

Calls end when you leave the conversation, switch desktops, or put the app in
the background. Ending a call does not stop an agent task that voice already
started; use **Stop** if you also want to cancel that task.

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
   computer), then tap **Request pairing**.
5. **Allow it on the computer.** Once the phone scans, the QR code disappears
   and the computer shows which phone scanned it. Click **Allow** if it's
   yours, or **Deny** if it isn't. The phone shows **Waiting for desktop
   approval** until you do. You can still change **Phone permissions**
   before you allow it.

The QR code works once and expires after a few minutes; click **New QR code**
for another. Scanning it alone gives a phone nothing until you allow it on the
computer. If the QR code is already gone when you go to scan it, another device
got there first: click **Deny** and make a new one.

### Pair more than one computer

You can pair the same phone with several computers, for example your laptop
and a home server. Open **Settings**, tap the computer at the top, and tap
**Pair another desktop**, then scan or paste that computer's invitation as
above. Pairing a computer the phone already knows replaces its old entry
instead of adding a second one.

The phone is connected to one computer at a time. Its name appears under the
**SUZENT** title, and **Chats** and **Tasks** show that computer's
conversations and scheduled tasks. To switch, open **Settings**, tap the
computer at the top, and pick another one. If it can't be reached, you stay
where you are. Swipe left on a computer in that list to forget it on the
phone.

Each computer keeps its own permissions for the phone. Everything under
**This desktop** in **Settings** (**Permissions**, **Enable foreground Node**,
**Pair again**, and **Forget this desktop**) applies to the computer you're
connected to.

### Using it away from home

The phone talks to your computer directly; there's no Suzent cloud in between.
On your home Wi-Fi that just works. To use it elsewhere, put both devices on
[Tailscale](https://tailscale.com/), go through a [relay you deploy
yourself](#through-your-own-relay), or give Suzent a public HTTPS address of
your own. Your computer has to be on and running Suzent; the
[background service](./automation.md#keep-suzent-running-in-the-background)
keeps it running after you quit the desktop app.

### Through your own relay

A relay lets the phone reach your computer from any network without a VPN or
port forwarding. Your computer connects out to the relay and keeps that
connection open; the phone sends its requests to the relay, which passes them
down. Suzent has no hosted relay: you run
[suzent-relay](https://github.com/cyzus/suzent-relay) yourself, for free on
Cloudflare Workers or with Docker on any server. Its README walks through each
option.

Everything between the phone and your computer is end-to-end encrypted. The
QR code carries your computer's key, and the phone checks it before sending
anything, so the relay only passes on data it can't read or change.

1. Deploy suzent-relay and note its `https://` address. Setting a
   registration key is recommended, so only your Suzent can use the relay.
2. On your computer, open **Settings → Devices → Relay**, enter the **Relay
   address** and **Registration key**, and save. The status changes to
   **Connected**.
3. Pair the phone by scanning a new QR code. The code now includes the relay.

The phone always tries your computer's direct addresses first and only uses
the relay when none of them answers. A phone paired before you set up the relay
learns about it the next time it connects to your computer directly.

**Reset relay addresses** issues new relay addresses. Use it if another Suzent
took over the address, or to cut off phones and webhook callers that have the
old one; pair the phone again afterwards. The same relay also gives
[webhook tasks](./automation.md) an address on the internet.

## What you can do on the phone

- **Find a chat.** On a phone, the bar at the bottom has **Chats**, **Tasks**,
  and **Settings**. **Chats** opens on your conversations, with a search icon
  and a yellow **New conversation** icon at the top right and **SUZENT Regent**
  below them. Switch between **Recent** (pinned chats, then your conversations newest first) and
  **Projects** (tap one to open it). **Load more** brings in older chats. The
  app remembers which list you last used. Tap the search icon to open a search page that looks
  through the titles of every chat the phone may read, not only the ones
  already loaded. Going back from a chat you opened there returns to the
  results, and **Cancel** returns to **Chats**. On a tablet, the lists sit in a
  sidebar on the left, with **Settings** and the yellow **New conversation**
  icon in its header and search below them. On
  an iPad, the sidebar button next to **Settings** hides it so a chat can use the
  full width.
- **Talk to the agent.** Send messages, watch replies stream in with their
  sources and an activity summary you can expand for each tool's details, and
  stop a reply, or redirect or queue a follow-up while it works. Long-press a message to copy or share it, edit and resend your
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
- **See what the agent made.** Images, videos and speech the agent creates,
  and videos or pictures it looked at for you, appear under its reply as on the
  computer. Videos and audio play with the phone's own player. Each file is
  fetched from your computer the first time you see it, so it needs the
  computer to be reachable then, and it works through your relay too.
- **Pick the model.** **Desktop model** lists the models you've enabled on
  your computer.
- **Answer approvals.** When the agent needs permission, **Approval required**
  appears above the message box with **Allow once** and **Reject** for each
  request.
- **Organize.** Long-press a chat to pin, rename, move, or delete it, or swipe
  it to pin or delete, if the phone has **Full control** (or may manage
  conversations).
- **Use what the agent shows.** Tables, cards, buttons, forms and the other
  displays the agent builds for you appear right in its reply, as on the
  computer. Tap a button or fill in a form to answer; your choice shows as a
  short line in the chat and the agent carries on from it. When the agent asks
  you a question with options, answer it there and the reply continues. Using
  them needs the **Send messages** permission. Displays the agent pins to the
  computer's side panel still appear in the reply on the phone.
- **See the plan and context.** In a conversation, tap the panel icon next to
  **New conversation** to open **Conversation info**: the goal the agent is
  working toward, its steps with what's done and what's next, and how full the
  context window is, split by what fills it. On a phone it opens as a sheet you
  can drag up for more; on a tablet it sits beside the chat. It's read-only and
  updates while the agent works. Regent's chat doesn't have it; its board stays
  on the computer.
- **Follow background work.** Sub-agent chats fold under the chat that
  started them. **Tasks** (on an iPad, the third list beside **Recent** and **Projects**; on an Android tablet, **Scheduled tasks** in the list) shows failed tasks first, then active and
  paused ones, with their status and next run. You can open a task's chat but
  not change the task from the phone.

The app is in English and Simplified Chinese. Under **Settings → Preferences**
you can choose **Appearance** (match the phone, light, or dark), **Text size**,
whether to use **Haptics**, and the **Language** (on iPhone this opens iOS
Settings for Suzent; on Android it needs Android 13 or later). These apply to
the phone only. If the connection drops, it reconnects when you open it again and
picks up a reply where it left off. If it can't, **Connection help** has
**Pair again**, **Forget connection**, and a way to switch to each other
computer you've paired.

## Change or remove access

On your computer, **Paired phones** under **Mobile access** lists each phone
by name with what it may do. Click **Edit permissions**, pick another choice
(or **Custom**), and **Save**; the phone keeps working with the new permissions straight away.
**Revoke access** cuts the phone off immediately: the next time it connects, it
signs out and asks you to pair again.

Click **Rename** to give a phone a name you'll recognize, then **Save**. This
helps with iPhones, which only tell the computer "iPhone". The name the phone
reported still shows in small text next to the platform, and your name stays
when the phone pairs again. Clear the field and save to go back to the phone's
own name.

**Forget this desktop** in the app's **Settings** (or **Forget connection** in
**Connection help**) removes that computer from the phone and also asks the
computer to revoke the phone's access; other paired computers stay. If the
computer can't be reached at that moment, click **Revoke access** there
yourself. Pairing the same phone again replaces its old entry instead of
adding a second one.

## Limits

The preview doesn't yet have:

- notifications, so the phone stays quiet until you open the app;
- the computer's side panel for displays the agent keeps updating (they show in the reply instead);
- memory, settings, or tool permissions, which stay on the computer;
- offline access to your conversations.

For the technical design, see the
[mobile architecture](../08-developing/architecture/mobile.md).
