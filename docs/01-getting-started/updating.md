---
sidebar_position: 4
title: Updating
description: How to update Suzent, repair shortcuts, and what to check when upgrading an existing install across versions.
---

# Updating Suzent

## Automatic updates

Suzent keeps itself up to date. Every few hours it checks for a new release and
downloads it in the background while you keep working. The new version is
installed the next time Suzent closes or starts, which takes a few seconds,
and the desktop app tells you once it has been updated. If Suzent runs as a
background service with no desktop app open, it installs the update between
3 and 5 a.m. when no chat has been active for 30 minutes.

To turn this off, uncheck **Update automatically** in Settings → About, or run:

```bash
suzent auto-update off      # or: on, status
```

Setting `SUZENT_AUTO_UPDATE=0` in the environment also turns it off.

Some updates are never installed automatically. Suzent leaves those to you
(use the Update button or `suzent update`):

- a new major version;
- an install with local changes to Suzent's own files;
- a source checkout, which follows the development branch;
- an update that failed twice, after which Suzent stays on the version that works.

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

**Your existing `MEMORY.md` won't be overwritten.** `MEMORY.md` is now a short
map of links to notebook pages (see
[MEMORY.md is a map](../03-features/memory/README.md#memorymd-is-a-map)), and
Suzent no longer rewrites it. To convert an older file, run
`suzent memory cleanup`: it writes a suggested map and the other fixes next to
your memory for you to review, and changes nothing until you apply them.

**Expect a large diff in your notebook after the first few dreams.** Suzent adds
review dates and confirmation counts to existing pages. If your notebook is in
Git or a sync folder, that churn is expected.

**Search results may be ordered differently.** Facts you've confirmed often or
written yourself now rank higher, and outdated ones lower. Nothing is removed.

**Repeated facts no longer appear in daily logs.** A fact that only repeats
something already recorded is counted instead of written again. The counts are
kept in `notebook/.state/confirmations.jsonl`.
