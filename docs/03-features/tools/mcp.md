---
sidebar_position: 11
title: MCP servers
description: Connect tools from any MCP server, by URL or by the command that starts it, and choose which conversations use them.
---

# MCP servers

Suzent can use tools from any [MCP](https://modelcontextprotocol.io/) server,
such as a database, an issue tracker, or a company API. A server is either a web
address (URL) or a program on your computer that Suzent starts (stdio).

## Adding a server

1. Open **Settings → MCP Servers** and click **Add** on the **Add new server** card.
2. Choose **URL** or **Stdio** and, if you like, type a **Name (optional)**.
   Without one, Suzent uses the URL's host or the command.
3. Fill in the details for that kind of server:

| Kind | What to enter |
|---|---|
| **URL** | The server's address, such as `https://host/path`, plus any headers it needs, written as `Header-Name=value` and separated by commas. Use this for an API key, for example `Authorization=Bearer abc123`. |
| **Stdio** | The command that starts the server (such as `uv`, `npx`, or `python`), its arguments separated by commas, and any environment variables as `KEY=value, KEY2=value2`. |

4. Click **Add Server**. Suzent connects right away and shows **Reachable** with
   the number of tools it found, or **Unreachable** with the reason. The server
   is saved either way, and it starts out enabled.

## Testing and editing

Each server in **Configured Servers** has three icon buttons, **Test**, **Edit**,
and **Remove** (hover to see their names). **Test** connects again and lists the server's tools.

A stdio server started with `npx` or `uv` may download its package the first
time it runs, so the check made when you add it can time out. Wait a minute and
click **Test**, which allows more time.

## Choosing where a server is used

The switch next to each server in **Settings → MCP Servers** turns it on or off.
You can also flip servers from a chat: open the sidebar, choose the **Tools**
tab, and find them under **MCP Servers**, below the built-in tools. Flipping a
server there changes the same switch in Settings.

[Chat apps](../../05-chat-apps/README.md) can use a different set: in
**Settings → Social Channels**, under **MCP Servers**, pick **Custom** instead of
**System Default** and choose the servers.

## How the agent uses MCP tools

Every tool from an enabled server is available to the agent, named after the
server so you can tell where it came from. MCP tools don't appear as separate
checkboxes in the tool picker, and they run without an approval prompt, so only
add servers you trust.

## From the command line

`suzent mcp` lists, adds, tests, enables, disables, and removes servers, using
the same list as Settings. See [Command line](../../07-reference/cli.md#mcp-servers).
