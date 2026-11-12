# Running Suzent in Harbor and Pier

These agents let benchmarks built on [Harbor](https://github.com/harbor-framework/harbor)
or its fork [Pier](https://github.com/datacurve-ai/pier) run Suzent as the
coding agent. [FrontierHarness Eval](https://frontierharness.org/) uses Harbor
for its Terminal-Bench tasks and Pier for its DeepSWE tasks.

| File | Role |
|---|---|
| `suzent_agent.py` | Harbor agent |
| `suzent_pier_agent.py` | Pier agent |
| `suzent_common.py` | What both share: install and run commands, model routing |
| `usage_proxy.py` | Logs the token usage of every model call |

For each trial an agent:

1. Installs `uv`, fetches Suzent from GitHub and runs `uv sync` in the task
   container.
2. Runs the task with `suzent run --json --permission-mode full_access` in the
   container's working folder, with the Docker sandbox off.
3. Reports input, output and cached token counts to the runner.

## Usage

Run the runner from this folder so it can import the modules:

```bash
cd examples/harbor
export MOONSHOT_API_KEY=...
harbor run -d terminal-bench-sample@2.0 -m moonshot/kimi-k3 \
  -a suzent_agent:SuzentAgent
```

```bash
pier run -p /work/deep-swe/tasks/<task> -m moonshot/kimi-k3 \
  --agent-import-path suzent_pier_agent:SuzentAgent
```

Pin the Suzent version with the agent keyword option, `--ak version=<ref>`.
It accepts a branch, a tag or a commit, and defaults to `main`. The version
must include this folder, because the usage proxy runs from the installed
checkout.

## Tasks without internet access

DeepSWE tasks run in containers that cannot reach the internet. Pier handles
this for an installed agent in two ways, and the Pier agent uses both:

- The install steps run while the task image is built, when the network is
  still available.
- At run time the container may reach only the hosts the agent lists. The
  agent lists one: the model provider.

## Models

Pass the model with `-m`. Every `*_API_KEY` and `*_BASE_URL` variable in the
environment the runner uses is forwarded to the container.

| `-m` value | How Suzent runs it | Per-call usage log |
|---|---|---|
| `fireworks_ai/<model>` | OpenAI-compatible provider at `api.fireworks.ai`, with `FIREWORKS_API_KEY` | Yes |
| `moonshot/<model>` | Moonshot provider at `api.moonshot.cn`, or `MOONSHOT_BASE_URL` | Yes |
| `openai/<model>` with `OPENAI_BASE_URL` set to another host | OpenAI-compatible provider at that host | Yes |
| `openai/<model>` | OpenAI provider at `api.openai.com` | No |
| anything else | Passed to Suzent unchanged as `<provider>/<model>` | No |

Moonshot keys work on one regional platform only. For a key from the
international platform, set `MOONSHOT_BASE_URL=https://api.moonshot.ai/v1`.

OpenAI's own endpoint is reached directly, because Suzent routes prompt caching
per conversation only when it sees that host, and a proxy in between would
change the caching being measured.

With Pier, a provider in the last row gets no network access, so use one of
the others for tasks without internet.

## Per-call usage

Suzent reports one token total per run. Benchmarks that price each model call
separately need more, so for the providers marked above the agent starts
`usage_proxy.py` in the container and points Suzent at it. The proxy forwards
every request unchanged and writes one line per chat completion to
`suzent-usage.jsonl`:

```json
{"t": 1794430000000, "status": 200, "prompt": 9120, "completion": 88, "cached": 8704}
```

`prompt` includes `cached`. A call that returned no usage is logged with
`"prompt": null`.

FrontierHarness Eval reads per-call usage through
`skills/frontierharness-eval/scripts/usage_details.py`. A harness that is not
registered there gets no turn count and no first-call cost, so add an entry:

```python
def _suzent(text: str) -> Detail:
    usages = []
    for event in _jsonl(text):
        total = event.get("prompt")
        if total is None:
            continue
        if int(total) or event.get("completion"):
            usages.append((int(total), int(event.get("cached") or 0)))
    return _detail(usages)

REGISTRY["suzent"] = ("suzent-usage.jsonl", _suzent)
```

## Tools and code mode

The agents run with Suzent's file and shell tools only: reading, writing,
editing and searching files, and running commands. Web, memory, media and
scheduling tools are left out, because every tool definition is resent on each
model call and a terminal coding task does not use them. Code mode is off,
whatever the saved setting is.

Change either with the runner's agent keyword option, for example
`--ak tools=ReadFileTool,RunCommandTool` or `--ak code_mode=true`. Report both
with any result you publish, since they are part of the harness configuration
being measured.

## What ends up in the trial's agent logs

| File | Content |
|---|---|
| `suzent.json` | The reply, the token totals and the conversation ID |
| `suzent-usage.jsonl` | Token usage of each model call |
| `suzent.log` | Server output and the names of the tools called |
| `usage-proxy.log` | Proxy errors, normally empty |
| `chats/` | The full conversation as JSONL |

## Limits

- Neither agent has run a task inside a real Harbor or Pier installation yet.
  The Harbor agent loads and constructs under Harbor 0.25.0; the Pier agent
  follows `BaseInstalledAgent` on Pier's `main` branch and has not been loaded
  by Pier. FrontierHarness Eval pins Harbor 0.22.0 and Pier 0.3.1, which may
  differ.
- The proxy reaches the provider with Python's default certificate store. A
  runtime that intercepts TLS, as Runta does to inject the provider key, has
  to make its certificate authority trusted inside the task container.
- The install needs a container image that can run Python 3.12 from `uv`.
