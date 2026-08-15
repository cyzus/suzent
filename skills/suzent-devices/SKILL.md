---
name: suzent-devices
description: Operate phones, laptops, headless servers, and peer agents connected to Suzent. Use for discovering devices, inspecting capabilities, invoking remote hardware commands, transferring returned files, or triggering a linked Suzent agent.
---

# Companion Devices

The product and CLI call connected companion devices **nodes**. Prefer the
`suzent nodes` CLI in host mode. Use the local REST API when running in a sandbox,
writing an integration, or accessing a route the CLI does not expose.

## Workflow

1. List connections and resolve the target by `display_name` or stable ID.
2. Describe the target before invocation when its capabilities are not already known.
3. Choose `invoke` or `trigger` deliberately.
4. Pass explicit JSON-serializable parameters.
5. Inspect the bounded result and handle returned file references correctly.

Never guess that a device supports a capability. Handle no-device, ambiguous-name, offline,
timeout, and rejected-pairing states explicitly.

## Invoke versus trigger

Use **invoke** for a specific advertised device capability:

```text
suzent nodes invoke <node-or-peer> camera.snap format=png
suzent nodes invoke <node-or-peer> speaker.speak text="Hello world"
```

Use **trigger** to ask a linked peer's Suzent agent to reason, use tools, and return a
conversational response:

```text
suzent nodes trigger <peer> "inspect the latest logs and summarize the failure"
```

Do not use `trigger` as an indirect replacement for a known hardware command.

## Quick reference

```text
suzent nodes list
suzent nodes status
suzent nodes describe <node-or-peer>
suzent nodes invoke <node-or-peer> <command> key=value
suzent nodes trigger <peer> <prompt>
```

Read `references/protocol.md` when pairing devices, using REST, downloading peer files,
or troubleshooting discovery and connection state.

## File results

Local invokes may return a local path. Peer invokes return a downloadable `file` object
with a local-server URL. Download the URL through the local Suzent server; never expose
or attempt to use a raw path from the remote peer's filesystem.

Invocations and peer prompts remain subject to the normal permission policy. Treat camera,
microphone, clipboard, shell, and file capabilities as sensitive even when a node advertises
them.
