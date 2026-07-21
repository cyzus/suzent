# WeChat Integration

Suzent can receive and reply to WeChat messages through Tencent's iLink Bot HTTP API.

## Setup

1. Install or enable the WeChat ClawBot/OpenClaw flow for your account.
2. Start Suzent with WeChat enabled and no `bot_token` to trigger QR login.
3. Scan the QR code URL printed in the server logs.
4. After login succeeds, copy the returned `bot_token` and `base_url` into `config/social.json` so the connection survives restarts.

## Configuration

Add the following to your `config/social.json`:

```json
"wechat": {
    "enabled": true,
    "bot_token": "YOUR_WECHAT_ILINK_BOT_TOKEN",
    "base_url": "https://ilinkai.weixin.qq.com",
    "channel_version": "1.0.2",
    "get_updates_buf": "",
    "allowed_users": []
}
```

## Notes

- WeChat replies require the latest inbound `context_token`, so Suzent can reply to conversations that have messaged it during the current process.
- Text receive/send is supported. Media receive is preserved as attachment metadata, and encrypted CDN upload/download support is not implemented yet.
- To find your WeChat sender ID for `allowed_users`, send the bot a message and check the Suzent log line for the unauthorized sender.
