---
sidebar_position: 3
title: Files
description: How your agent reads documents, creates and edits files, and finds files by name or content.
---

# Files

The **Filesystem** tools let the agent read your files, write new ones, make
precise edits, and search a folder. They work on the folders it is allowed to
reach: its project library, the shared folder, and any folders you mount. See
[Workspace & sandbox](../filesystem.md) for which folders those are and how to
add your own.

| Tool | What it does | Can be turned off |
|---|---|---|
| **Read File** | Opens a file and reads it | No, always on |
| **Glob** | Finds files by name, such as `**/*.csv` | No, always on |
| **Grep** | Searches inside files for a word or pattern | No, always on |
| **Write File** | Creates a file, or replaces one completely | Yes |
| **Edit File** | Changes part of an existing file | Yes |

## Reading files

Plain text and code files are read with line numbers, up to 2,000 lines at a
time. For longer files the agent reads the next part by asking for a line range,
so it can work through a big log or data file in pieces.

Documents are converted to text first, so the agent can read:

- PDF files
- Word documents
- Excel spreadsheets
- PowerPoint presentations

Files larger than 50 MB can't be read, and other binary files (such as programs
or archives) are refused rather than read as garbled text. To understand what is
in a picture, the agent uses your **Vision** model instead; see
[Model roles](../../04-models/model-roles.md).

Very long results are shortened to 30,000 characters. The agent is told where
the full text was saved, so it can read the rest if it needs to.

## Writing and editing

**Write File** creates a file, including any missing folders on the way, or
replaces an existing file with entirely new content. If the file already has
exactly that content, nothing is changed.

**Edit File** changes one piece of a file without rewriting the rest. The agent
names the exact text to replace and the text to put in its place:

- **The text must match.** Small differences in trailing spaces, line endings,
  or curly versus straight quotes are tolerated. Anything else and the edit
  fails, so the agent reads the file again and retries.
- **The text must be unique.** If it appears more than once, the edit stops
  until the agent includes more of the surrounding text, or asks to replace
  every occurrence.
- **No silent overwrites.** If the file changes on disk while the edit is being
  applied, the edit is cancelled so newer content isn't lost.

Edits keep the file's existing text encoding and line-ending style. Binary files
and files larger than 50 MB can't be written or edited.

## Finding and searching

**Glob** finds files by name pattern: `*.py` matches files in one folder,
`**/*.py` also looks in every subfolder. It lists up to 100 matches.

**Grep** searches the contents of files using a pattern. The agent can limit
it to certain file types, ignore upper and lower case, and show a few lines
around each match. Files over 2 MB are skipped.

Both skip folders that are usually noise, such as `.git`, `node_modules`,
`.venv`, `build`, and `dist`.

## Approval

Reading, finding, and searching never ask for approval. Writing and editing
depend on the [permission mode](./human-in-the-loop.md#permission-modes):

| Mode | **Write File** and **Edit File** |
|---|---|
| **Ask** | Asks you every time |
| **Smart** | Run on their own inside the conversation's working folder; anywhere else is checked by the reviewer |
| **Full Access** | Run without asking |

The working folder is the project library, or the folder you chose with
**Working Dir**.

## Undoing changes

File changes made with **Write File** and **Edit File** are rolled back when
you retry the agent's last turn. See
[Undoing the last turn](../filesystem.md#undoing-the-last-turn-retry). Files
changed by shell commands are not covered; see [Commands](./shell.md).
