---
sidebar_position: 4
title: Feishu (Lark)
description: Connect a Feishu (Lark) custom app so you can talk to your agent from Feishu.
---

# Feishu (Lark)

## Set up

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

Once it's connected, see [Chat apps](./README.md) for who can talk to the bot,
which model it uses, and keeping it online.
