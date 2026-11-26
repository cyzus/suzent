"""Running the agent's own JavaScript on a page it was allowed to script."""

import json

from suzent.tools.base import ToolErrorCode, ToolResult

SCRIPT_TIMEOUT_MS = 15_000
MAX_RESULT_CHARS = 10_000
MAX_ERROR_CHARS = 1_000
WRONG_SITE = "suzent-wrong-site:"
TIMED_OUT = f"timed out after {SCRIPT_TIMEOUT_MS // 1000}s"


def script_expression(site: str, code: str) -> str:
    """Wrap *code* as an async function body that only runs on *site*.

    The origin check is a top-level statement ahead of the code, so a throw
    ends the whole script: code that closes the wrapper early to add its own
    top-level statements still never runs on another site, and a navigation
    after the approval cannot move the code elsewhere.
    """
    return f"""if (location.origin !== {json.dumps(site)}) {{
  throw new Error({json.dumps(WRONG_SITE)} + location.origin);
}}
(async () => {{
  const value = await Promise.race([
    (async () => {{
{code}
    }})(),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error({json.dumps(TIMED_OUT)})), {SCRIPT_TIMEOUT_MS})
    ),
  ]);
  let text;
  try {{
    text = value === undefined ? "undefined" : JSON.stringify(value) ?? String(value);
  }} catch {{
    text = String(value);
  }}
  // Cut here, so a huge result never crosses the bridge whole.
  return text.length > {MAX_RESULT_CHARS}
    ? text.slice(0, {MAX_RESULT_CHARS}) + `... [truncated, ${{text.length}} chars]`
    : text;
}})()"""


def script_result(value: object) -> ToolResult:
    text = value if isinstance(value, str) else json.dumps(value)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"... [truncated, {len(text)} chars]"
    return ToolResult.success_result(
        f"run_js returned: {text}", metadata={"command": "run_js"}
    )


def script_error(site: str, message: str) -> ToolResult:
    if WRONG_SITE in message:
        actual = message.split(WRONG_SITE, 1)[1].split()[0][:200]
        return ToolResult.error_result(
            ToolErrorCode.INVALID_ARGUMENT,
            f"The page is on {actual}, not {site}. Call run_js again with site {actual}.",
        )
    if TIMED_OUT in message:
        # Page code cannot be cancelled once started, so it may still act.
        return ToolResult.error_result(
            ToolErrorCode.TIMEOUT,
            f"run_js {TIMED_OUT}, but the code may still be running in the page "
            "and change it later. Call snapshot to see what it did before running "
            "it, or anything that repeats it, again.",
        )
    return ToolResult.error_result(
        ToolErrorCode.EXECUTION_FAILED,
        f"run_js threw: {message[:MAX_ERROR_CHARS]}",
    )


def script_stopped(message: str) -> ToolResult:
    """DevTools refused or cut the evaluation, as it does to code that runs too long."""
    return ToolResult.error_result(
        ToolErrorCode.EXECUTION_FAILED,
        f"run_js did not finish ({message[:200]}). Code is stopped after "
        f"{SCRIPT_TIMEOUT_MS // 1000}s.",
    )
