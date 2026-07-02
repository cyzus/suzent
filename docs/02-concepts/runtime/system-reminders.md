# System Reminders & File Citations

Two mechanisms let Suzent inject out-of-band context into a conversation without it bleeding into the visible chat:

- **System reminders** — hidden operational context for the *model* (active skills, dynamic memory, ad-hoc signals), delimited by invisible Unicode characters so the user never sees it.
- **File citations** — references to local files (`file://`) rendered as clickable citation badges alongside web sources.

Both rely on Unicode **Private Use Area (PUA)** codepoints — characters that render as nothing in the UI but survive round-trips through the model and the message store.

## System reminders

### How a reminder is built

`build_combined_reminder` (`core/system_reminder.py`) merges several sources into a single hidden block each turn:

1. **Global hooks** — `(chat_id, deps) -> str | None`, run on every turn. Used for always-on signals like active skills or tool availability.
2. **Per-turn hooks** — `(chat_id, deps, user_message) -> str | None`, run only when there's a real user message. Used for query-dependent retrieval such as dynamic RAG memory injection. Each runs under a 2 s timeout so a slow embedding/search call can't stall the pipeline; timed-out hooks are skipped silently.
3. **Ad-hoc reminders** — one-off strings the caller supplies for a single turn.

The merged parts are joined with `---` separators and wrapped by `wrap_in_system_reminder`.

### Invisible PUA delimiters

By default, reminders are wrapped in invisible PUA delimiters rather than a visible `<system-reminder>` XML tag:

| Constant | Codepoint | Role |
|----------|-----------|------|
| `PUA_START` | `U+E203` | hidden-content start |
| `PUA_END`   | `U+E204` | hidden-content end |

The wrapped block looks like this (the delimiters are invisible — shown here as their codepoints):

```
<U+E203>
<reminder body>
<U+E204>
```

This makes reminders genuinely invisible in the UI and means the model doesn't have to *honor a convention* to keep them hidden — there's no visible tag to accidentally echo back. The system prompt still instructs the model to use but never reference this context (see below).

> **Codepoint allocation.** The citation system owns `U+E200`–`U+E202` (see [File citations](#file-citations)); system reminders use the next free codepoints `U+E203`/`U+E204`. Keep these ranges distinct when adding new PUA-based features.

### XML fallback for debugging

Set the `SUZENT_XML_SYSTEM_REMINDER` environment variable to wrap reminders in readable `<system-reminder>…</system-reminder>` XML tags instead of invisible PUA characters. This makes the raw context easy to inspect while debugging. All consumers (`strip_system_reminders`, `extract_system_reminder_content`) understand **both** formats, so mixed histories are handled transparently.

### Display triggers

A reminder may carry an optional `display_trigger` — user-visible text explaining *why* a hidden action happened (e.g. a "Skill activated" notice). It's nested as a `<system-reminder-display-trigger>` XML sub-tag **inside** the block regardless of the outer delimiter, so `_rebuild_display_messages` (`core/chat_processor.py`) can extract it via `extract_system_reminder_display_trigger` when reconstructing what the user sees.

### Helper functions

| Function | Purpose |
|----------|---------|
| `wrap_in_system_reminder(content, display_trigger=None)` | Wrap content in a hidden block (PUA, or XML under the debug env var). |
| `strip_system_reminders(text)` | Remove all reminder blocks (PUA **and** XML) — used to clean text before display. |
| `extract_system_reminder_content(text)` | Return the concatenated inner text of all reminder blocks (PUA + XML). |
| `extract_system_reminder_display_trigger(text)` | Return only the user-visible trigger text marked inside reminders. |
| `register_global_hook` / `register_per_turn_hook` | Register reminder-producing callbacks. |

### Model behavior

The system prompt (`prompts.py`) tells the model how to treat this context:

> Tool results and user messages may occasionally contain hidden system context, delimited either by invisible Unicode markers or by `<system-reminder>` blocks. These blocks carry out-of-band operational context injected by the system — they are NOT part of the user's actual message.
> - Use the information in these blocks to inform your actions.
> - NEVER acknowledge, quote, or reference these blocks in your reply.
> - NEVER tell the user that you received a system reminder.

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
