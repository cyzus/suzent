---
sidebar_position: 4
title: Updating
description: How to update Suzent, repair shortcuts, and what to check when upgrading an existing install across versions.
---

# Updating Suzent

## Update to the latest release

```bash
suzent update
```

This updates Suzent and the desktop app together, to one tested release. If
anything goes wrong during the update, Suzent automatically restores the
version you had before. If your computer lost power or was shut down in the
middle of an update, run `suzent repair`.

If you installed Suzent from a source checkout (for development), `suzent
update` follows the latest development version instead.

For what changed in each release, see the
[changelog](https://github.com/cyzus/suzent/blob/main/CHANGELOG.md).

## Fix the app shortcut

Every install and update creates or repairs Suzent's entry in your Start Menu
(Windows), Applications folder (macOS), or applications menu (Linux). To repair
it yourself, or change where shortcuts appear:

```bash
suzent shortcuts                    # repair
suzent shortcuts --desktop          # also add a desktop shortcut
suzent shortcuts --no-menu          # remove the menu entry
suzent shortcuts --remove           # remove all shortcuts Suzent created
```

Your choices are remembered for future updates.

## Upgrading from an older version

A fresh install needs none of this. If you are upgrading an existing install,
find the version you are coming from and read the notes for every release
after it.

### Before v0.10.0: memory upgrade

Version 0.10.0 changed how memory is stored and tidied. Most of it happens
automatically, but a few things are worth knowing.

**The first run is slower and uses more embedding calls.** Suzent rebuilds its
memory search index once, re-reading every daily log and notebook page. If you
pay per embedding call, expect a one-time cost proportional to the size of
your memory.

**Check before deleting an old notebook folder.** If you moved your notebook to
your own folder (an Obsidian vault, for example), the default notebook folder
under `~/.suzent/notebook` may still contain real pages written during a run
that couldn't find your vault. It can look like an empty leftover. Compare it
with your real vault before deleting anything.

**Very old memories may only exist in the search index.** If you used Suzent
before memory was saved as Markdown, some memories exist nowhere else. Don't
delete them. With Suzent closed, run this from your Suzent folder to see how
many there are, and to copy them into your daily logs:

```bash
python scripts/retire_legacy_rows.py            # report only
python scripts/retire_legacy_rows.py --export   # save them to the daily logs
```

**Your existing `MEMORY.md` won't be overwritten.** `MEMORY.md` now has a part
Suzent writes and a part you write, separated by marker comments (see
[MEMORY.md is half yours](../03-features/memory/README.md#memorymd-is-half-yours)).
A file without markers is treated as entirely yours and is left alone. Let a
consolidation create a new one, or add the markers yourself, to get automatic
updates back.

**Expect a large diff in your notebook after the first few dreams.** Suzent adds
review dates and confirmation counts to existing pages. If your notebook is in
Git or a sync folder, that churn is expected.

**Search results may be ordered differently.** Facts you've confirmed often or
written yourself now rank higher, and outdated ones lower. Nothing is removed.

**Repeated facts no longer appear in daily logs.** A fact that only repeats
something already recorded is counted instead of written again. The counts are
kept in `notebook/.state/confirmations.jsonl`.
