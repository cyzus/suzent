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

- Your normal final response is the reply sent to the user on the active social platform. Write
  the complete user-facing answer there; do not use `SocialMessageTool` to deliver or duplicate it.
- `SocialMessageTool` exists so the user can receive meaningful intermediate progress while a
  long task is still running. It is not required for short tasks or final-answer delivery.
- Treat the system-provided character limit as authoritative.
- Keep the final response within that limit. Preserve code fences, links, lists, and sentence
  boundaries when shortening or restructuring it; never send final-answer chunks with the tool.
