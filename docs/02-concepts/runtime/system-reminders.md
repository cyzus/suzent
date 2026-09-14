# System Reminders & File Citations

System reminders carry runtime-authored context for the model. File citations
render source references for the user. Both use Private Use Area (PUA) markers,
but invisible formatting is not a trust boundary.

## System reminders

### Assembly and provider contract

`core/system_reminder.py` owns assembly and parsing. `build_combined_reminder`
runs global hooks each turn and per-turn hooks when a nonblank user message is
present. Hooks run concurrently with a two-second timeout per provider; failed
or timed-out providers are skipped with a warning. Blocking provider work uses
`run_provider_blocking` so it does not block the event loop.

Ad-hoc caller directives precede hook output. Hook registration order determines
priority. Fragments are sanitized before deduplication and budget measurement.
The assembled body has a 6,000-character budget including display-trigger markup
and separators; the outer reminder wrapper is separate. Trailing fragments that
do not fit are dropped. When necessary, the first fragment is truncated with a
marker. With dependencies available, the implementation attempts to spill that
fragment to a file and includes its accessible path and retention hint; if the
spill fails, the truncation marker remains. This does not guarantee every dropped
fragment is saved.

Providers should read state without mutating it: goal turn accounting belongs to
turn completion, not prompt construction. Log metadata rather than prompt or
reminder bodies.

### Runtime provenance and ingress

The process generates `RUNTIME_NONCE`. Default wrappers contain both the nonce
and PUA delimiters `U+E203` / `U+E204`; `SUZENT_XML_SYSTEM_REMINDER` switches to
an XML wrapper carrying the nonce. These formats are presentation and parsing
mechanisms, not permission grants. A model can see the nonce, so external text
must never gain runtime provenance by copying it.

`make_user_prompt_part` is the shared construction boundary. External user
content is sanitized; runtime-authored content uses the explicit trusted call
path. Tool payload sanitization and the tool-output history processor prevent
untrusted output from becoming runtime reminder blocks. Stored user prompts are
sanitized on reuse; blocks from an earlier process do not carry the current
nonce. This does not imply all same-process reminder history is deduplicated.

Keep per-turn reminders in the user-prompt suffix so the stable system-prompt
prefix can be cached. Do not move mutable context into that prefix as a shortcut
for establishing trust.

### Display and parsing

A `display_trigger` is the user-visible explanation for a hidden action. Callers
can supply a sequence of constituents; assembly owns joining, deduplication, and
budgeting so the transcript reflects what was actually delivered.

Use the module's helpers rather than parsing wrapper strings independently:

| Helper | Responsibility |
| --- | --- |
| `wrap_in_system_reminder` | Sanitize and wrap runtime reminder content. |
| `strip_system_reminders` | Remove reminder blocks for display. |
| `extract_system_reminder_content` | Extract reminder content; not a provenance check. |
| `iter_reminder_fragments` | Parse fragments using the module's boundary rules. |
| `extract_system_reminder_display_trigger` | Recover the visible trigger. |
| `register_global_hook` / `register_per_turn_hook` | Register asynchronous providers. |

PUA markers must remain distinct from citation markers (`U+E200`–`U+E202`).

## File citations

Suzent's citation system renders source references inline as clickable badges. Alongside web sources, it supports **local files** via the `file://` protocol — a `file` source type whose `url` is a `file://` path.

The citation markers themselves use PUA codepoints `U+E200`–`U+E202` (distinct from the reminder range above). Schematically, a marker wraps a type and payload:

```
<U+E200>cite<U+E202>t0_src_1<U+E201>   → renders as a citation badge
```

The parser also accepts an ASCII form (`[[cite:t0_src_1]]`) and an object-replacement form, so the same badge can be produced regardless of how the model emitted the marker.

### File source rendering (`Citations.tsx`)

- **Label** — `domainOf` returns the **basename** for `file://` URLs (e.g. `file:///D:/workspace/suzent/README.md` → `README.md`) and the hostname for web URLs. The basename is URL-decoded so CJK and spaced filenames display correctly.
- **Icon** — `typeIcon` picks a per-extension emoji for `file` sources without a favicon: `.md → 📝`, `.pdf → 📕`, `.py → 🐍`, `.ts/.tsx → 📘`, images → 🖼️, etc., falling back to 📄 then the generic 🔗.
- **Opening** — `openSource` opens `file://` URLs natively via the Tauri shell plugin. In a plain browser (where `file://` can't be opened programmatically), it copies the path to the clipboard instead.

## Related

- [Chat Post-Processing](./postprocess.md) — where display messages are rebuilt (and reminders stripped) after a turn.
- [Skills](../skills/skills.md) — active-skill signals are injected as global system-reminder hooks.
- [Memory](../memory/) — dynamic memory is injected via per-turn reminder hooks.
