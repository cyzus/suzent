# Filing memory pages

How to type and place pages that hold memory: facts about the user, lessons from past
work, and knowledge about the world. Read it whenever you file one, whether you are the
memory dream or an agent asked to remember something.

## Page types

Every page declares `type:` in its frontmatter. Memory is found by type, not by folder,
so a user can rename or renumber folders without losing anything.

| `type:` | Holds |
|---|---|
| `personal` | facts about the user, in the user's own terms |
| `experience` | lessons from past work: the situation, what was tried, the outcome, the lesson |
| a knowledge type from `schema.md` (`concept`, `entity`, ...) | facts about the world, with a source |

A page about the user with no `type:` gets `type: personal`. Something the agent made,
proposed or designed is never on a `personal` page.

## Choosing a folder

`schema.md` belongs to the user. Do not edit it to record where things go. Pick the
folder in this order and stop at the first that answers:

1. `schema.md` names a folder for this kind of page. Use it.
2. Pages of this type already exist (grep the vault for `type: <type>`). Put it beside them.
3. Otherwise choose the existing folder whose purpose in `schema.md` fits best, and add a
   subfolder named for the type if that keeps it apart (for example `Experience/` under
   the knowledge area).

Never create a new numbered top-level folder: those numbers are the user's layout. A
folder that only the agent fills is a sign step 3 picked badly.

## Defaults in the example schema

A vault seeded from `schema_example.md` uses `3_Personal/` for `personal`,
`2_Wiki/Experience/` for `experience`, and the `2_Wiki/` subfolders for knowledge types.
These are examples of step 1, not rules for other vaults.
