---
name: nodes
description: Interact with companion devices (phones, laptops, headless servers) connected to suzent via the CLI.
---

## Overview

The Nodes skill lets you control remote companion devices connected to the suzent server. Nodes are devices that connect via WebSocket and advertise capabilities (commands) you can invoke.

Use the `BashTool` with `suzent nodes` commands to:
- Discover connected devices and their capabilities
- Run commands on remote devices (take photos, run scripts, get clipboard, etc.)
- Check device connectivity status

## Commands

### List connected nodes

```bash
suzent nodes list
```

### Show node connectivity summary

```bash
suzent nodes status
```

### Describe a node's capabilities

```bash
suzent nodes describe <node_id_or_name>
```

### Invoke a command on a node

```bash
# Option 1: Key-Value Pairs (Simpler)
suzent nodes invoke <node_id_or_name> <command> key=value [key2=value2 ...]

# Option 2: JSON Params (Legacy/Complex)
suzent nodes invoke <node_id_or_name> <command> --params '{"key": "value"}'
```

## Examples

```python
# List what devices are available
result = bash_tool(command="suzent nodes list")

# Check what a specific node can do
result = bash_tool(command="suzent nodes describe MyPhone")

# Take a photo on a connected phone (simple key=value)
result = bash_tool(command='suzent nodes invoke MyPhone camera.snap format=png')

# Speak with arguments (inferred types: string, int, bool)
result = bash_tool(command='suzent nodes invoke "Local PC" speaker.speak text="Hello world" prompt=cheerful')

# Run a command on a remote desktop (JSON still useful for complex structures)
result = bash_tool(command='suzent nodes invoke MacBook system.run --params \'{"command":"ls -la"}\'')
```

## Best Practices

- Always run `suzent nodes list` first to see what's available before invoking.
- Use display names (e.g., "MyPhone") rather than UUIDs for readability.
- Pass `--params` as valid JSON; omit if the command takes no arguments.
- Handle the case where no nodes are connected gracefully.
- Node commands require the suzent server to be running.
