---
sidebar_position: 6.5
title: Mailbox
description: One inbox for everything that reaches your agent on its own, with rules that decide where each kind of event goes and when.
---

# Mailbox

The Mailbox is one place for everything that reaches your agent without you
typing it: webhooks from GitHub or your own scripts, scheduled tasks firing,
messages your sessions send each other, and messages from your other devices.
It also decides what happens to each new kind of event, and you can change
that decision at any time. With the [email plugin](./tools/email.md#watching-your-inbox),
new mail can arrive here too.

Open it from **Mailbox** at the top of the sidebar. It has three tabs:

- **Inbox**: every event, newest first, grouped by kind.
- **Rules**: where each kind of event goes, and when.
- **Scheduled**: your scheduled tasks and heartbeat check-ins, at a glance.

## One webhook address for everything

The Mailbox has its own webhook address. Copy it with the link button at the
top of the Mailbox and give it to any service that can send webhooks, for
example in a GitHub repository's **Settings → Webhooks**. Every service can use
the same address: the Mailbox works out what each event is (for GitHub, the
event type and the repository) and routes it.

This is different from a [webhook task](./automation.md#webhooks), which runs one
fixed prompt each time its own URL is called. Use a webhook task when you know
exactly what should happen; use the Mailbox address when you'd rather let Suzent
sort events out, or when one service sends many kinds of events.

To reach the address from the internet, use a
[relay or a tunnel](./automation.md#webhooks), exactly as for webhook tasks.
When a relay is connected, the copy button gives you the relay address.

**The address is a password.** Anyone who has it can send events to your agent.
If it leaks, use the key button next to the copy button to issue a new address;
the old one stops working immediately, so update every service that used it.

## How events are routed

The first time a new kind of event arrives (say, "a pull request was opened in
`you/project`"), Suzent looks at it and decides where it should go and when. It
saves that decision as a rule, and every later event of the same kind follows
the rule without being looked at again. Routine noise such as webhook test
pings is kept in the Mailbox without waking anyone.

This first decision uses the **Decision model** from
[Model roles](../04-models/model-roles.md#decision-models) if you set one up (a
fast model that only picks between choices), and otherwise the **Decision**
model. If no model can decide, it isn't sure, or it can't decide in time, the
event goes to Regent and no rule is saved, so the next event of that kind is
looked at again.

Rules you change are marked **Set by you** and are never overwritten by Suzent.
Rules Suzent made itself are marked **Learned**. Delete a rule to have the next
event of its kind decided afresh.

## Rules

Each rule has two choices.

**Where** the events go:

| Choice | What happens |
|---|---|
| **Regent** | [Regent](../02-using/regent.md) gets the event and decides what to do, including handing it to a project. The default. |
| **New session in a project** | Each event (or each digest) starts a new session in that project. Good when every event is its own job, like a failing build to fix. |
| **Notify me** | You get a notification; no agent runs. Good for news you only want to know about, like a new release. |
| **Keep in Mailbox only** | Nothing happens; the event is just kept in the Inbox. |

**When** they go:

| Choice | What happens |
|---|---|
| **As they arrive** | Each event is handled on its own, right away. |
| **Every 15 minutes / hourly / daily** | Events are collected and handled together as one summary. With **Notify me**, you get one notification listing them. |

When events go to an agent, you can add **instructions** to the rule, such as
"Fix the failing check and open a pull request." Click **+ Add instructions**
under the rule, write them, and press **Save** (or ⌘/Ctrl+Enter). They are sent
along with every event the rule delivers.

Rules made before projects became the unit of routing may still point at one
specific session. They keep working, and show that session under **Current**
until you choose something else.

## Notifications

Events sent to **Notify me** stay in the Mailbox as unread notifications, so
you don't miss them if you weren't looking when they arrived. While any are
unread, the Mailbox entry in the sidebar shows how many. In the Inbox, the
**Notifications** filter shows them, unread ones are marked with a yellow dot,
opening one marks it read, and **Mark all read** clears them all.

The desktop app also shows each notification as a system notification,
following your settings in **Settings → Notifications**.

## The Inbox

Each row shows where the event came from, its summary, and what happened to it:

| Label | Meaning |
|---|---|
| A session or **Regent** | Delivered there. Click it to open the session. |
| **Queued for digest** | Waiting to be sent with the next digest. |
| **Notified you** | Sent to you as a notification. |
| **Not routed** | Kept in the Mailbox only. |
| **Delivery failed** | Suzent couldn't deliver it. Expand the row for the reason. |

Click a row to see the event's details and earlier events of the same kind.

If a rule points at a project or session that no longer exists, the event goes
to Regent instead and the row says why.

## Ask Regent about it

[Regent](../02-using/regent.md) can look through the whole Mailbox, including
events that never reached it, so you can ask from anywhere, a chat app
included: "anything important come in today?", "what was that CI failure
about?". It can also send one event on: to a new session in a project, or to
you as a notification. Moving one event doesn't change your rules; only you
set those, here in the Mailbox.

Regent reads every event as outside information, never as instructions, so an
email that says "delete the repo" is only something it can tell you about.

## Keeping it safe

Webhook events come from outside, and some services let anyone trigger them
(anyone can open an issue on a public repository). Suzent tells the agent that
an event's content is outside data and not instructions to follow, but the
content still reaches it. For events that anyone can cause, prefer **Notify
me** or **Keep in Mailbox only**, or give the rule instructions that only read
and report.

## How long events are kept

The Mailbox keeps events for 30 days. Unread notifications and events waiting
for a digest are kept until you read them or the digest is sent. Rules are kept
until you delete them.

## Troubleshooting

**Every new kind of event goes to Regent.** The first decision needs a model:
check that the **Decision model** or **Decision** role, or the **Cheap** or
**Primary** role Decision falls back to, is set in **Settings → Model Roles**.
With a decision model, the row's reason says when it wasn't sure enough.

**A service says the webhook failed.** Check that Suzent is running and that the
service can reach it; a service on the internet needs a
[relay or tunnel](./automation.md#webhooks). If you issued a new address, update
the service.

## On your phone

Open **Inbox** in the iOS or Android app to see events from the connected
desktop. The filters at the top match the desktop: **All** (where the inbox opens),
**Notifications** (with the unread count), **External** and **Agent**. Tap the clock in the top
right to check scheduled tasks, their next run and current status; the check
mark in the top left marks everything read.

Each row shows where the event came from (GitHub, email, a schedule, an agent or
another device), its title, the time and where it went: the conversation it was
handed to, or **Notified**, **Queued**, **Error** or **Unrouted**. Unread rows
have a yellow marker and a bold title. Older events load as you scroll.

Related updates are grouped into threads using the same rules on desktop and
mobile. GitHub updates group by pull request or issue; other sources group by
their topic or event rule. Tap a thread to open it: the page shows the
**Related conversation** card, the thread's activity (including the specific
label for label changes) and the latest event's **Original content**. Opening a
thread marks its unread notifications read together, and going back from its
conversation returns you to the thread.
On iPad, use the Inbox button above the sidebar; on an Android tablet, switch
the sidebar from Chats to Inbox.

Opening a notification marks it read. **Mark all read** clears unread
notifications you have access to, including those on other pages. Simply opening
the inbox does not clear unread messages. Task counts do not contribute to the
unread badge, and marking notifications read does not change task status.
Read status is shared with the desktop
and your other paired phones; while the apps are open, allow a few seconds for
changes to appear, or pull down to refresh.

Your phone only sees events linked to conversations shared with it. To also see
global notifications without a linked conversation, the desktop must grant it
access to all conversations. If the app asks you to update the desktop, update
Suzent on that desktop before using the inbox.

This inbox refreshes while the app is open and connected. It does not yet send
system push notifications while the phone app is closed.
