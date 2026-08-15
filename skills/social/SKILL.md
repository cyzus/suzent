---
name: social
description: Adapt responses and progress updates for Telegram, Slack, Discord, Feishu, or WeChat social-channel conversations. Use when the active conversation is on a social platform or the user requests platform-specific message formatting.
---

# Social Messaging

Read only the active platform's reference:

- Telegram: `references/telegram.md`
- Slack: `references/slack.md`
- Discord: `references/discord.md`
- Feishu or Lark: `references/feishu.md`
- WeChat: `references/wechat.md`

Use the injected platform and recipient; do not guess. If the platform is unknown, use only
the generic rules.

## Generic rules

- Treat the system-provided character limit as authoritative.
- Split only at safe boundaries, preserving code fences, links, lists, and sentences.
- Use `SocialMessageTool` only for meaningful progress on long tasks. Final responses deliver
  automatically; never resend them with the tool.
