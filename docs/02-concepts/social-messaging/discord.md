# Discord Integration

Suzent supports full integration with Discord, allowing you to chat with the agent via Direct Messages (DMs) or in channels.

## Setup Guide

### 1. Create a Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give it a name (e.g., "Suzent").
3. Go to the **Bot** tab and click **Add Bot**.

### 2. Configure Intents
Suzent requires **Privileged Gateway Intents** to read messages.
1. Scroll down to the **Privileged Gateway Intents** section on the Bot tab.
2. Enable **Message Content Intent**.
3. (Optional) Enable **Server Members Intent** if you want more robust user recognition, but it's not strictly required.
4. Save Changes.

### 3. Get the Token
1. Click **Reset Token** on the Bot page.
2. Copy the token. This is your `DISCORD_TOKEN`.

### 4. Invite the Bot
1. Go to the **OAuth2** tab > **URL Generator**.
2. Select scopes: `bot`.
3. Select bot permissions: `Read Messages/View Channels`, `Send Messages`, `Attach Files`.
4. Copy the generated URL and open it in your browser to invite the bot to your server.

## Configuration

Add the following to your `config/social.json` (Environment variables are no longer supported):

```json
"discord": {
    "enabled": true,
    "token": "YOUR_DISCORD_TOKEN_HERE",
    "allowed_users": []
}
```

### Access Control
To find your Discord User ID:
1. Enable **Developer Mode** in Discord (User Settings > Advanced).
2. Right-click your username and select **Copy ID**.
3. Add this ID to the `allowed_users` list in `config/social.json`.
