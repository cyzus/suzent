# Slack Integration

Suzent integrates with Slack using **Socket Mode**.

## Quick Setup (Recommended)

The easiest way to configure the Slack App is using the App Manifest. This ensures all permissions and settings (including the tricky "Messages Tab") are correct.

### 1. Create a Slack App
1. Go to [Slack API Apps](https://api.slack.com/apps).
2. Click **Create New App** > **From an app manifest**.
3. Select your workspace.
4. Choose **YAML** format.
5. Paste the following Manifest:

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

6. Click **Next** and **Create**.

### 2. Generate App Token
1. Go to **Basic Information** > **App-Level Tokens**.
2. Click **Generate Token and Scopes**.
3. Name it `socket` and add the `connections:write` scope.
4. Copy the **App Token** (`xapp-...`).

### 3. Install App
1. Go to **Install App** in the sidebar.
2. Click **Install to Workspace**.
3. Copy the **Bot User OAuth Token** (`xoxb-...`).

> [!IMPORTANT]
> **Reinstall Required on Changes**
> If you change ANY settings in the future (like enabling a new permission), you **MUST** go to **Install App** and click **Reinstall to Workspace** for changes to take effect. If you see "Sending messages is turned off", you likely need to reinstall.

---

## Configuration

Add the tokens to your `config/social.json` (Environment variables are no longer supported):

```json
"slack": {
    "enabled": true,
    "app_token": "xapp-...",
    "bot_token": "xoxb-...",
    "allowed_users": []
}
```

> [!NOTE]
> **Context Awareness**
> Suzent is smart enough to handle **Threads**. If you reply to the bot in a thread, it will reply back in that same thread. If you talk in a channel, it will reply in the channel.

### Access Control
To find your Slack User ID:
1. Click on your profile picture in Slack.
2. Click **Profile**.
3. Click the three dots (...) > **Copy Member ID**.
4. Add this ID to the `allowed_users` list.
