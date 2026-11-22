# suzent-acp

Use [Suzent](https://suzent.com) from editors that support the
[Agent Client Protocol](https://agentclientprotocol.com/), such as Zed or
JetBrains IDEs.

Suzent must be installed and running on the same computer. This package is a
small launcher: it finds that installation and starts its built-in ACP agent,
so every session is a real Suzent conversation with your memory, skills,
models and permission rules.

```sh
uvx suzent-acp
```

Your editor runs this command for you. When it asks you to sign in, choose
**Pair with Suzent** and approve the request in Suzent under
**Settings → ACP Agents → Editor connections**.

Suzent is found in this order: the `SUZENT_DIR` folder, the folder chosen in
the Suzent installer, `~/suzent`, then `suzent` on `PATH`. Options are passed
through to `suzent acp`, for example `uvx suzent-acp --permission-mode full_access`.

See [Use Suzent from your editor](https://suzent.com/docs/features/nodes#use-suzent-from-your-editor-acp).
