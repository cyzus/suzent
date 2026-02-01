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

Or use Environment Variables:
-   `TELEGRAM_TOKEN`: Your Telegram Bot API Token.
-   `ALLOWED_SOCIAL_USERS`: Your User ID.
