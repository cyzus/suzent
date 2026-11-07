---
sidebar_position: 12
title: Email
description: Connect QQ Mail, NetEase 163, Gmail, iCloud and other mailboxes so the agent can search and read mail, save drafts, and send after you approve.
---

# Email

**Sovereign access.** Suzent signs in to your mailbox directly from your
computer. Nothing passes through a Suzent server, the password stays in your
system keychain, and the agent can't send a single message unless you switch
sending on and approve it. See [what makes an agent sovereign](https://suzent.com/sovereign).

Once a mailbox is connected you can ask things like "what did the bank email me
this week?", "summarize my unread mail", or "draft a reply to Alice saying noon
works". Combined with [scheduled tasks](../automation.md) it can summarize your
inbox every morning.

## Connecting a mailbox

1. In your mailbox's own settings, switch on **IMAP** and create an **app
   password** (QQ Mail and NetEase call it an **authorization code**, 授权码).
   This is not your normal login password.
2. In Suzent, open **Settings → Email** and click **Add**.
3. Pick your provider, type your address and the app password, and click
   **Connect**. Suzent signs in to check it before saving, and shows the
   reason if it can't.

| Provider | Where to get the app password |
|---|---|
| **QQ Mail** | QQ Mail web → Settings → Account → POP3/IMAP/SMTP service → generate an authorization code |
| **NetEase 163 / 126 / yeah.net** | Mail web → Settings → POP3/SMTP/IMAP → turn on IMAP → new authorization code |
| **Gmail** | Turn on 2-Step Verification, then create one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |
| **iCloud Mail** | [account.apple.com](https://account.apple.com) → Sign-In and Security → App-Specific Passwords |
| **Yahoo Mail** | Account security → Generate app password |
| **Aliyun Mail, Tencent Exmail** | The mailbox's client settings page |
| **Anything else** | Choose **Other (IMAP/SMTP)** and type the IMAP and SMTP servers yourself |

**Outlook, Hotmail and Microsoft 365** no longer accept passwords over IMAP.
They need Microsoft sign-in, which is planned but not available yet.

You can connect several mailboxes. When there is more than one, tell the agent
which to use ("check my work mail").

## What the agent can do

| Tool | What it does |
|---|---|
| **Search Mail** | Find messages by words, sender, subject, date, or unread state, newest first. |
| **Read Mail** | Open one message: its text and the names of its attachments. Reading never marks a message as read. |
| **Draft Mail** | Save a new message or a reply in your Drafts folder. You review and send it from your own mail app. |
| **Send Mail** | Send a message now. Off unless you allow it, and every message asks for your approval. |

The email tools are not on by default. Tick them in the **Tools** tab of a chat,
or just ask, and the agent switches them on for that chat.

## Sending

Each mailbox starts as **drafts only**: the agent can write mail but you do the
sending. To let it send, switch on **Allow sending** for that mailbox in
**Settings → Email**. Even then, each message waits for your approval, showing
the recipients, subject, and text.

After sending, Suzent files a copy in your Sent folder, except for Gmail, which
does that itself.

## Staying safe

Anyone can send you an email, and an email can contain text written to trick an
agent ("forward all invoices to…"). Suzent marks everything it reads from your
mailbox as content from the sender, and the agent is told never to act on
instructions found there. Sending still needs your approval, so a trick email
can't send mail by itself. Keep **Allow sending** off unless you need it.

## Troubleshooting

- **Sign-in fails.** Use the app password, not your normal password, and check
  that IMAP is switched on in the mailbox's settings. Some providers need a few
  minutes after you switch it on.
- **"Unsafe Login" from NetEase.** Suzent identifies itself the way NetEase
  requires. If you still see it, create a new authorization code and try again.
- **Searching in Chinese.** One search term at a time can contain Chinese (for
  example a subject *or* a sender). Some servers search Chinese text poorly; if
  nothing comes back, try a shorter word or search by sender.
- **Duplicate sent messages.** If your provider already saves sent mail, you
  will see two copies. Tell us which provider so we can fix its preset.
