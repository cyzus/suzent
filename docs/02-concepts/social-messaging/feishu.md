# Feishu (Lark) Integration

## Setup

### 1. Create an App
Go to the [Feishu Developer Console](https://open.feishu.cn/app) (or Lark Helper) and create a **"Self-built App"** (Custom App).

### 2. Permissions (Scopes)
Go to **Permissions & Scopes** and enable the following:

```
{
  "scopes": {
    "tenant": [
      "contact:user.base:readonly",
      "im:chat",
      "im:chat:read",
      "im:chat:update",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.p2p_msg:readonly",
      "im:message:send_as_bot",
      "im:resource"
    ],
    "user": []
  }
}
```

### 3. Event Subscriptions (CRITICAL)
This is distinct from Permissions. You must explicitly tell Feishu to push messages to you.

1.  Go to **Events & Callbacks** > **Event Configuration**.
2.  Set **Subscription Method** to **"Long Connection"** (WebSocket).
    *   *Note: This removes the need for a public URL/Webhook.*
3.  Click **"Add Event"**.
4.  Search for **"Message received"** (Key: `im.message.receive_v1`) and add it.
    *   *Without this, the bot will connect but receive NO messages.*

### 4. Publish (CRITICAL)
Feishu changes do **not** take effect until you publish a new version.

1.  Go to **Version Management & Release**.
2.  Click **Create Version**.
3.  Enter a version number (e.g., `1.0.0`) and description.
4.  Click **Save** and then **Publish**.
    *   *If you change permissions or events later, you must Publish again.*

### 5. Credentials
Go to **Credentials & Basic Info** to get your `App ID` and `App Secret`.

---

## Configuration

Add the following to your `config/social.json`:

```json
{
  "feishu": {
    "enabled": true,
    "app_id": "cli_...",
    "app_secret": "...",
    "allowed_users": ["ou_..."] 
  },
  "allowed_users": [] 
}
```

## Finding Your User ID

1.  Start the Suzent server with your config.
2.  Send a message (e.g., "Hi") to the bot on Feishu.
3.  Check the server logs for a line like:
    *   `Unauthorized social message from: Feishu User (ou_c50b7b...)`
    *   OR `Feishu Message IDs - Union: ..., Open: ou_c50b7b..., ...`
4.  Copy the **Open ID** (starts with `ou_`).
5.  Add it to the `allowed_users` list in `config/social.json` and **Restart the Server**.
