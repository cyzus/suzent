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

For personal pages:

- `stale_after` is required, derived from the fact category per `schema.md`. It is what gives
  a revisit pass something to select on; a claim with no expiry is never re-examined.
- The per-claim confirmation marker plays the role of OKF `sources[].usage_count`, kept inline
  because these claims are bullets on a shared page rather than one document each. A repeated
  fact is a ranking signal, not new knowledge.
- A user editing a fact directly is a `human:` actor and outranks anything the extractor
  produced. Record it as `verified` only if you actually observed that edit.
