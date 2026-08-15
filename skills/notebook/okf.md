# OKF-inspired profile

Source: [Open Knowledge Format v0.2 specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).

Use this profile only when `schema.md` opts in. The schema remains authoritative.
This improves portability but does not make the vault OKF-conformant; never add `okf_version`
or claim conformance.

For synthesized concept pages:

- Require `type`. Prefer `title`, `description`, and `tags` when useful for navigation.
- Use `status: draft | stable | deprecated` for lifecycle. Keep local review state in a
  separate field such as `review: current | needs-review`.
- Add `sources` only for materials actually used. Each entry requires `resource`; add a stable
  `id` when body claims use matching Markdown footnotes.
- Add `stale_after: YYYY-MM-DD` only when the knowledge has a meaningful expiry date.
- Use standard Markdown links with vault-relative paths for portable concept links.
- Preserve unknown frontmatter keys. Emit `generated` or `verified` only when the actor and
  verification event are known; never infer them.
