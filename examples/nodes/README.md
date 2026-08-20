# Non-Suzent Nodes

**Joining the Suzent mesh does not require running Suzent.** A node is any device
that speaks a small JSON-over-WebSocket protocol. `suzent node host` is the
reference client, not a requirement.

[`minimal_node.py`](./minimal_node.py) is a complete node in ~100 lines whose
only dependency is `websockets`.

```bash
pip install websockets
python minimal_node.py --name "Living Room TV" --url ws://192.168.1.10:25314/ws/node
```

Then approve the device in Suzent (Settings → Devices). Save the `device_token`
you get back and pass it with `--token` to reconnect silently.

## The whole protocol

```
→ {"type":"connect","display_name":"Living Room TV","platform":"tvos",
   "capabilities":[{"name":"tv.play","description":"...","params_schema":{"title":"str"}}],
   "device_token":"<optional, from a previous approval>"}

← {"type":"pending","pairing_code":"85TGSS"}      # new device, awaiting approval
← {"type":"connected","node_id":"...","device_token":"..."}

← {"type":"invoke","request_id":"...","command":"tv.play","params":{"title":"..."}}
→ {"type":"result","request_id":"...","success":true,"result":{...}}

← {"type":"ping"}   →   {"type":"pong"}
```

Rules worth knowing:

- **Always answer an `invoke`.** A node that stays silent just makes the caller
  time out. Report failure with `{"success": false, "error": "..."}`.
- **Namespace capability names** (`tv.play`, not `play`) so they stay unambiguous
  across a mesh of many devices.
- **The server rejects commands you didn't advertise**, so the manifest is a real
  contract, not a hint.
- **Authorization is the device token**, minted by your approval — not by being
  Suzent. See [security.md](../../docs/02-concepts/nodes/security.md).

## The hard part isn't the protocol — it's where the code runs

For an iPhone or a TV, implementing the above is trivial. Keeping a process alive
to hold the socket is not:

| Device | Reality |
|---|---|
| **iPhone / iPad** | iOS suspends background apps. A Shortcut can't hold a WebSocket. You need a real app, or a bridge (below). |
| **Smart TV** | Most TVs won't run arbitrary code at all. Roku, webOS, and Tizen expose *their own* network APIs instead. |
| **Apple TV / Chromecast** | No third-party daemons; both are controlled from outside. |
| **Raspberry Pi / NAS / mini PC** | Runs `minimal_node.py` directly. This is the easy case. |
| **ESP32 / microcontroller** | Ideal fit — a tiny WS client, no MCP stack needed. |

### The bridge pattern (recommended for TVs and phones)

Run **one** node on something always-on — a Pi, NAS, or desktop — and have it
advertise capabilities it implements by calling each device's native API:

```python
CAPABILITIES = [
    {"name": "tv.play",     "params_schema": {"title": "str"}},
    {"name": "lights.set",  "params_schema": {"room": "str", "level": "int"}},
    {"name": "phone.notify","params_schema": {"text": "str"}},
]

async def handle_invoke(command, params):
    if command == "tv.play":
        # Roku ECP is plain HTTP; webOS is a WebSocket; Apple TV via `pyatv`.
        httpx.post(f"http://{ROKU_IP}:8060/search/browse", params={"keyword": params["title"]})
        return {"playing": params["title"]}
    if command == "lights.set":
        return hue.set_group(params["room"], params["level"])
    if command == "phone.notify":
        # iOS: a Pushcut / Shortcuts webhook is far easier than a background app.
        return httpx.post(PUSHCUT_URL, json={"text": params["text"]}).json()
```

Your agent sees one mesh member with clean capabilities; the messy
vendor-specific integration stays in one file you control.

## When to use MCP instead

A node and an MCP server are the same shape — a named, enumerable list of things
to invoke. Suzent already speaks MCP for tools.

- **Node protocol**: embedded and LAN devices, minimal footprint, operator
  pairing, works on a microcontroller.
- **MCP**: anything richer that already has (or wants) a standard tool interface.

Use A2A only when the far end is an *agent* you delegate goals to, rather than a
capability surface you invoke. See [a2a.md](../../docs/02-concepts/nodes/a2a.md).
