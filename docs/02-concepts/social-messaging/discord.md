---
sidebar_position: 3
title: Discord
description: Connect a Discord bot so you can talk to your agent in DMs and server channels.
---

# Discord

## Set up

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

Once it's connected, see [Chat apps](./README.md) for who can talk to the bot,
which model it uses, and keeping it online.
