---
sidebar_position: 1
title: Telegram
description: Connect a Telegram bot so you can talk to your agent from Telegram.
---

# Telegram

## Set up

1. Message [@BotFather](https://t.me/botfather), send `/newbot`, and follow the
   prompts. Copy the **bot token** it gives you.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric user ID.
3. In Suzent, paste the token, enable Telegram, and add your user ID to
   **Allowed users**.

To let the bot read every message in a group, not just mentions and commands,
send `/mybots` to @BotFather, choose your bot, then **Bot Settings → Group
Privacy → Turn off**, and add the bot to the group again.

Once it's connected, see [Chat apps](./README.md) for who can talk to the bot,
which model it uses, and keeping it online.
