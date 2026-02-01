# Telegram Integration

## Setup

1.  **Create a Bot**: Talk to [@BotFather](https://t.me/botfather) on Telegram to create a new bot and get your **Token**.
2.  **Get Your User ID**: Talk to [@userinfobot](https://t.me/userinfobot) to get your numeric User ID.

## Configuration

Add the following to your `config/social.json`:

```json
{
  "telegram": {
    "enabled": true,
    "token": "YOUR_TELEGRAM_BOT_TOKEN",
    "allowed_users": ["YOUR_USER_ID"]
  }
}
```


> [!IMPORTANT]
> **Group Privacy Mode**
> By default, Telegram bots cannot see messages in groups unless they are mentions or commands. To allow the bot to see all messages:
> 1. Talk to **@BotFather**.
> 2. Send `/mybots` > Select your bot > **Bot Settings** > **Group Privacy**.
> 3. Select **Turn off**.
> 4. Re-add the bot to the group if necessary.

> [!NOTE]
> Suzent now strictly uses `config/social.json` for credentials. Environment variables are no longer supported.
