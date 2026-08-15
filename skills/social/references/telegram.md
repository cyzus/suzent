# Telegram response rules

- Use standard Markdown; Suzent converts it to Telegram HTML. Keep tables narrow because they
  become preformatted text.
- The fallback chunker may break Markdown near the usual 4096-character limit. Pre-split long
  responses.
- Native option buttons, photos, and files are supported.
