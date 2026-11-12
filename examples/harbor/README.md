# Running Suzent in Harbor

`suzent_agent.py` is a [Harbor](https://github.com/harbor-framework/harbor)
agent. It lets Harbor-based benchmarks such as Terminal-Bench and
[FrontierHarness Eval](https://frontierharness.org/) run Suzent as the coding
agent.

For each trial it:

1. Installs `uv`, fetches Suzent from GitHub and runs `uv sync` in the task
   container.
2. Runs the task with `suzent run --json --permission-mode full_access` in the
   container's working folder, with the Docker sandbox off.
3. Reports input, output and cached token counts to Harbor.

## Usage

Run Harbor from this folder so it can import the module:

```bash
cd examples/harbor
export MOONSHOT_API_KEY=...
harbor run -d terminal-bench-sample@2.0 -m moonshot/kimi-k3 \
  --agent-import-path suzent_agent:SuzentAgent
```

Pin the Suzent version with Harbor's agent version option. It accepts a
branch, a tag or a commit, and defaults to `main`.

## Models

Pass the model with `-m` using Suzent's own model ID, `<provider>/<model>`.
Every `*_API_KEY` and `*_BASE_URL` variable in the environment Harbor runs in
is forwarded to the container.

A Fireworks route (`fireworks_ai/...`) is the one exception. Suzent has no
Fireworks provider, so the agent sends it through the OpenAI-compatible
provider at `https://api.fireworks.ai/inference/v1` with `FIREWORKS_API_KEY`.

## Tools

The agent runs with Suzent's file and shell tools only: reading, writing,
editing and searching files, and running commands. Web, memory, media and
scheduling tools are left out, because every tool definition is resent on each
model call and a terminal coding task does not use them.

To choose a different set, pass a comma-separated list with Harbor's agent
keyword option, for example `--ak tools=ReadFileTool,RunCommandTool`. Report
the tool set with any result you publish, since it is part of the harness
configuration being measured.

## Code mode

Code mode is off, whatever the saved setting is. Turn it on for a run with
`--ak code_mode=true`, and report it with the result like the tool set.

## What ends up in the trial's agent logs

| File | Content |
|---|---|
| `suzent.json` | The reply, the token usage and the conversation ID |
| `suzent.log` | Server and tool-call output |
| `chats/` | The full conversation as JSONL |

## Limits

- This agent has not been run against a real Harbor installation yet. It
  follows the `BaseInstalledAgent` interface on Harbor's `main` branch.
- Token usage is one total per run. Benchmarks that reprice the first model
  call's cached tokens need per-call usage, which Suzent does not report.
- Suzent names each new conversation with a separate model call. That call is
  not included in the reported usage.
- There is no adapter for Pier, which FrontierHarness uses for its DeepSWE
  tasks.
