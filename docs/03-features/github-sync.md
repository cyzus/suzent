---
sidebar_position: 9
title: GitHub Sync
description: Keep your agent's settings, skills, and memory in a private GitHub repository and carry them to another computer.
---

# GitHub Sync

**Sovereign continuity.** Portability is what lets an agent outlive the
computer it started on. GitHub Sync moves the parts that make up your agent,
while your API keys stay on each device, so moving to a new computer never
means shipping your keys. See
[what makes an agent sovereign](https://suzent.com/sovereign).

GitHub Sync keeps a copy of your agent in a private GitHub repository that you
own. Set it up on a second computer and the same agent, with the same memory
and skills, is there too.

## What syncs

| Synced | Stays on each device |
|---|---|
| Settings (`default.yaml`, `config.yaml`, `skills.json`) | API keys and provider sign-ins |
| Your own skills | `.env`, `local.yaml`, and other secrets |
| Memory and notebook (Markdown files) | Chat history, search indexes, caches |
| | MCP servers, permission rules, and device pairings |

Secrets are never uploaded. After setting up a new computer, add your API keys
there in **Settings → Providers**.

## Set up

1. Open **Settings → Data & Sync → GitHub Sync**.
2. Click **Sign in with GitHub**, open the link shown, and enter the code.
3. Accept the suggested repository name (`suzent-brain`) or type your own.
   Suzent creates it as a private repository if it doesn't exist.
4. Click **Quick start**.

On your other computer, repeat the same steps with the same repository name,
then **Pull** to bring everything down.

## Everyday use

Suzent compares your computer with the repository and shows what changed:

- **Push** appears when you have local changes to upload.
- **Pull** appears when the repository has changes to download.
- **Discard** undoes local changes you don't want to keep, one file or all.
- **Use cloud** replaces your local copy with the repository's version.

Click a file to see exactly what changed before you confirm. Anything that
would delete or overwrite memory always asks first.

Turn on **Auto-sync** to sync every few hours: Suzent pulls incoming changes and
pushes your own automatically, and still asks before deleting or replacing
memory.

## Troubleshooting

**A provider works on one computer but not another.** API keys don't sync, on
purpose. Add the key on the new computer.

**GitHub sign-in expired.** Sign in again from the GitHub Sync panel. This
sign-in is separate from your model provider keys.

**A pull says the branches have diverged.** Try again after a moment. If it
keeps happening, run **Quick start** again on a fresh local folder, and avoid
editing files in the sync folder (`~/.suzent/github-sync`) by hand.

**Upgrading from an older version that synced encrypted keys.** Older versions
could upload encrypted API keys. That is no longer supported, and the next push
removes them from the repository (they remain in its Git history). Make sure
each computer has its keys set locally before upgrading, and rotate any key you
think may have been exposed.
