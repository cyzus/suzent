---
name: suzent-desktop
description: Drive native desktop apps with Suzent's desktop plugin and the agent-desktop CLI. Use when asked to open, inspect, or operate a desktop application on this computer.
---

# Desktop apps

Use the `desktop` tool. Do not shell out to `agent-desktop`, and do not expect it to run inside the chat sandbox. The sandbox has no display. Every call runs on the host computer and can see and change the real desktop. There is no isolation.

Suzent does not install the CLI. If the tool says it is missing, stop and tell the user to install agent-desktop 1.0.x themselves (`npm install -g agent-desktop`, or a release binary from https://github.com/vercel-labs/agent-desktop/releases). On macOS they also need Accessibility permission: `agent-desktop permissions --guide`.

## Before the first action

Read the guide that matches the installed binary. Call `desktop` with command `skills`:

1. `subcommand` `get`, `skill` `desktop`
2. `subcommand` `get`, `skill` `platform`

Follow those instructions. They describe refs, verification, and what this operating system can and cannot do. Prefer them over memory if they disagree with this skill.

## Loop

1. `list-apps` or `list-windows` when the target is not already known.
2. `snapshot` the app. Start with `interactive_only` and `compact`. For a dense window, `skeleton` first, then `snapshot` again with `root` set to one ref.
3. Act on a qualified ref from that snapshot, such as `@s8f3k2p9:e8`. A bare `@e8` is invalid.
4. Snapshot again, or `get` / `is`, to check the result.

`find` is the right call when the role or name is already known.

## Approval and input

Reading (`snapshot`, `find`, `get`, `is`, list commands, `status`, `version`, `skills`, `wait`, clipboard get) does not ask. Anything that changes the desktop asks, and follows the chat's permission mode.

Leave `headed` false. That path uses the accessibility API and does not move the pointer or take focus. Set `headed` true only after a result says physical input is required (`POLICY_DENIED`). On Linux, pointer actions and window moves often need an X11 session; Wayland refuses them.

`ok: true` means the command returned, not that the app saved the change. Read `disposition`. Repeat an action only when `retry` is `safe`. `STALE_REF` and `AMBIGUOUS_TARGET` mean: snapshot again and use the new refs.

## Do not

- Do not guess pixels. Refs come from the latest snapshot.
- Do not use `key-down`, `key-up`, `mouse-down`, or `mouse-up`. Use `press`, `mouse-click`, or `drag`.
- Do not treat a partial snapshot (`complete` is false) as proof an element is missing.
- Do not put screenshots, clipboard text, or window contents into a place other people can read. Pass `path` when a screenshot should be saved, and remember that writing a path asks for approval.
