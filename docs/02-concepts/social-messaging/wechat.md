# WeChat Integration

Suzent can receive and reply to WeChat messages through Tencent's iLink Bot HTTP API.

## Setup

1. Install or enable the WeChat ClawBot/OpenClaw flow for your account.
2. Open **Settings → Social Channels** and enable WeChat.
3. Click **Log in with WeChat**.
4. Scan the QR code with WeChat. Suzent saves the returned `bot_token` and `base_url` into `config/social.json`, and adds the scanning `ilink_user_id` to WeChat's `allowed_users` when the API returns it.

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
- QR login authenticates Suzent to the WeChat iLink service. `allowed_users` is still the sender allowlist for incoming messages. The scanner is auto-added when `get_qrcode_status` returns `ilink_user_id`; add more WeChat sender or group IDs only if you want other conversations to access Suzent.
