---
name: social
description: Social messaging guidelines for Telegram, Slack, Discord, and Feishu. Best practices for formatting, character limits, and platform-specific features.
---

# Social Messaging Guide

## Platform Formatting

### Telegram
- Supports Markdown (bold, italic, code, links)
- Message limit: 4096 characters
- Supports inline buttons (not available via SocialMessageTool)
- Good for short, punchy updates with formatting

### Slack
- Uses mrkdwn format (different from standard Markdown)
- *bold* uses `*text*`, _italic_ uses `_text_`
- Message limit: ~40,000 characters
- Supports blocks and attachments

### Discord
- Standard Markdown formatting
- Message limit: 2000 characters
- Code blocks with syntax highlighting
- Keep messages short — split long content into multiple messages

### Feishu
- Rich text via post format, plain text via text
- Message limit: ~30,000 characters

## Best Practices
- Keep messages concise for chat context
- Use SocialMessageTool for progress updates on long tasks
- Break long responses into logical sections
- Avoid large code blocks on mobile-first platforms (Telegram)
- Send a brief acknowledgment before starting long-running operations
- Your final answer is delivered automatically — use the tool only for intermediate updates
