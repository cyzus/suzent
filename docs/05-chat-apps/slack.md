---
sidebar_position: 2
title: Slack
description: Connect a Slack app in Socket Mode so you can talk to your agent from Slack, with no public URL.
---

# Slack

Suzent connects to Slack in Socket Mode, so it needs no public URL.

## Set up

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

Once it's connected, see [Chat apps](./README.md) for who can talk to the bot,
which model it uses, and keeping it online.
