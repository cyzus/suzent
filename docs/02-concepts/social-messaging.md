---
sidebar_position: 7
title: Chat apps
description: Talk to your agent from Telegram, Slack, Discord, Feishu (Lark), or WeChat.
---

# Chat apps

Talk to your agent from the chat apps you already use. It's the same agent,
with the same memory and files, whether you're at your desk or on your phone.

| App | Supports |
|---|---|
| [Telegram](#telegram) | Text, photos, files |
| [Slack](#slack) | Text, files, threads |
| [Discord](#discord) | Text, files, DMs and channels |
| [Feishu (Lark)](#feishu-lark) | Text, files |
| [WeChat](#wechat) | Text, images |

## How it works

1. Create a bot in the app (steps for each app are below).
2. In Suzent, open **Settings → Social Channels**, pick the app, paste the
   bot's credentials on the **Connection** tab, and enable it.
3. On the **Access control** tab, add your own user ID to **Allowed users**.

Suzent keeps these settings in `config/social.json`, which you can also edit by
hand. `config/social.example.json` shows every option.

**Only people you allow can talk to your agent.** Messages from anyone not on
the app's allowed list are refused. Each app has its own list, and only user
IDs count; display names are ignored because anyone can change theirs. If you
turn on **Pairing & Access Control**, strangers can ask for access and you
approve or deny them in the same panel.

**Conversations persist.** Each chat becomes a regular Suzent conversation that
remembers its history, even after a restart. Photos are read by the model if it
supports images. Files you send are saved to the conversation's
`/persistence/uploads/` folder, where the agent can open them. Send `/retry` to
redo the agent's last answer.

To control which model and tools chat-app conversations use, see the
**Social Model** and **Agent Capabilities** sections on the same settings page.

Chat apps only work while Suzent is running. To keep them available after you
close the window, turn on the [background service](./automation.md#keep-suzent-running-in-the-background).

## Telegram

1. Message [@BotFather](https://t.me/botfather), send `/newbot`, and follow the
   prompts. Copy the **bot token** it gives you.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric user ID.
3. In Suzent, paste the token, enable Telegram, and add your user ID to
   **Allowed users**.

To let the bot read every message in a group, not just mentions and commands,
send `/mybots` to @BotFather, choose your bot, then **Bot Settings → Group
Privacy → Turn off**, and add the bot to the group again.

## Slack

Suzent connects to Slack in Socket Mode, so it needs no public URL.

1. Go to [api.slack.com/apps](https://api.slack.com/apps), click **Create New
   App → From an app manifest**, choose your workspace and **YAML**, and paste:

   ```yaml
   display_information:
     name: Suzent
     description: AI Agent Co-worker
     background_color: "#2c2d30"
   features:
     app_home:
       home_tab_enabled: true
       messages_tab_enabled: true
       messages_tab_read_only_enabled: false
     bot_user:
       display_name: Suzent
       always_online: true
   oauth_config:
     scopes:
       bot:
         - app_mentions:read
         - chat:write
         - files:write
         - im:history
         - im:write
         - users:read
   settings:
     event_subscriptions:
       bot_events:
         - app_mention
         - message.im
     interactivity:
       is_enabled: true
     org_deploy_enabled: false
     socket_mode_enabled: true
     token_rotation_enabled: false
   ```

2. Under **Basic Information → App-Level Tokens**, click **Generate Token and
   Scopes**, add the `connections:write` scope, and copy the **app token**
   (`xapp-...`).
3. Under **Install App**, click **Install to Workspace** and copy the **bot
   token** (`xoxb-...`).
4. In Suzent, paste both tokens and enable Slack.
5. To find your user ID, click your profile picture in Slack, open **Profile**,
   then **⋯ → Copy member ID**. Add it to **Allowed users**.

If you change any Slack app setting later, click **Install App → Reinstall to
Workspace**, or the change won't take effect. "Sending messages is turned off"
usually means it needs reinstalling.

Reply to the bot in a thread and it answers in that thread.

## Discord

1. In the [Discord Developer Portal](https://discord.com/developers/applications),
   click **New Application**, then open the **Bot** tab.
2. Under **Privileged Gateway Intents**, turn on **Message Content Intent** and
   save.
3. Click **Reset Token** and copy the **bot token**.
4. Under **OAuth2 → URL Generator**, select the `bot` scope and the
   **View Channels**, **Send Messages**, and **Attach Files** permissions.
   Open the generated URL to invite the bot to your server.
5. In Suzent, paste the token and enable Discord.
6. To find your user ID, turn on **Developer Mode** in Discord (**User Settings
   → Advanced**), right-click your name, and choose **Copy User ID**. Add it to
   **Allowed users**.

## Feishu (Lark)

1. In the [Feishu Developer Console](https://open.feishu.cn/app), create a
   **custom app** (self-built app).
2. Under **Permissions & Scopes**, enable:
   `contact:user.base:readonly`, `im:chat`, `im:chat:read`, `im:chat:update`,
   `im:message`, `im:message.group_at_msg:readonly`,
   `im:message.p2p_msg:readonly`, `im:message:send_as_bot`, and `im:resource`.
3. Under **Events & Callbacks → Event Configuration**, set the subscription
   method to **Long Connection**, then **Add Event** and add **Message
   received** (`im.message.receive_v1`). Without this event the bot connects
   but never receives messages.
4. Under **Version Management & Release**, create a version and **publish**
   it. Feishu ignores changes until they are published, so publish again after
   any later change.
5. Copy the **App ID** and **App Secret** from **Credentials & Basic Info**
   into Suzent and enable Feishu.
6. To find your user ID, send the bot a message. It will be refused, and the
   pending request (or Suzent's log) shows your **Open ID**, starting with
   `ou_`. Add it to **Allowed users**.

## WeChat

WeChat connects through Tencent's iLink bot service by scanning a QR code.

1. Make sure the WeChat ClawBot (OpenClaw) feature is available for your
   account.
2. In **Settings → Social Channels → WeChat**, click **Log in with WeChat**.
3. Scan the QR code with WeChat and keep the panel open until it connects.

Suzent saves the connection and adds the account that scanned the code to
**Allowed users** automatically. While the agent is working, WeChat shows its
typing indicator.

Current limits: Suzent can receive text and images and reply with text. It can
only reply to conversations that have messaged it since Suzent last started.
