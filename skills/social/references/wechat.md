# WeChat response rules

- Use plain text; Markdown, HTML, tables, and code-fence rendering are unsupported.
- Replies require a cached `context_token` from a recent inbound message. Do not send
  proactively without one. Suzent manages the typing indicator.
- Outbound media and native option buttons are unsupported. Incoming media may contain only
  metadata; do not claim inspection without an accessible attachment.
