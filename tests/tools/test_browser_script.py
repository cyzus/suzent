import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ApprovalRequired

from suzent.permissions.context import PermissionContext
from suzent.permissions.engine import PermissionEngine, ToolPermissionRequest
from suzent.permissions.models import CommandDecision, PermissionMode
from suzent.permissions.rules import parse_rules
from suzent.tools.browser import tool as tool_module
from suzent.tools.browser.config import site_origin
from suzent.tools.browser.script import script_error, script_expression
from suzent.tools.browser.tool import BrowsingTool, parse_batch_step

SITE = "https://shop.example"


def run_js(site: str | None = SITE, code: str = "return 1") -> dict:
    return {"command": "run_js", "arguments": [code], "site": site}


def context(tmp_path: Path, rules: list[dict] | None = None) -> PermissionContext:
    return PermissionContext(
        chat_id="chat-1",
        mode=PermissionMode.DEFAULT,
        interaction_profile="interactive",
        tool_approval_policy={},
        tool_permission_policies={},
        permission_rules=parse_rules(rules or []),
        path_resolver=SimpleNamespace(
            resolve=lambda value: Path(value),
            get_working_dir=lambda: tmp_path,
            get_base_dir=lambda: tmp_path,
        ),
        sandbox_enabled=False,
        transcript=[],
    )


def site_rule(behavior: str, site: str = SITE) -> dict:
    return {
        "tool": "browser_action",
        "behavior": behavior,
        "matcher": {
            "type": "exact_input",
            "value": {"command": "run_js", "site": site},
        },
    }


async def decide(args: dict, tmp_path: Path, rules: list[dict] | None = None):
    return await PermissionEngine().evaluate(
        ToolPermissionRequest("browser_action", args), context(tmp_path, rules)
    )


def test_sites_are_kept_the_way_the_page_spells_its_origin() -> None:
    assert site_origin("https://Shop.Example/cart?x=1") == SITE
    assert site_origin("https://shop.example:443") == SITE
    assert site_origin("http://localhost:8080/") == "http://localhost:8080"
    assert site_origin("https://bücher.de") == "https://xn--bcher-kva.de"
    for bad in ("shop.example", "file:///etc", "https://u:p@shop.example"):
        with pytest.raises(ValueError):
            site_origin(bad)


def test_run_js_needs_the_exact_origin_so_a_saved_site_always_matches() -> None:
    assert BrowsingTool.invalid_call_reason(run_js()) is None
    assert "https://shop.example" in BrowsingTool.invalid_call_reason(
        run_js(site="https://shop.example/cart")
    )
    assert "needs site" in BrowsingTool.invalid_call_reason(run_js(site=None))
    assert BrowsingTool.invalid_call_reason({"command": "click"}) is None


async def test_code_asks_first_and_can_be_allowed_for_one_site(
    tmp_path: Path,
) -> None:
    asked = await decide(run_js(), tmp_path)
    assert asked.behavior == CommandDecision.ASK
    remembered = next(a for a in asked.actions if a.id == "allow_global")
    assert remembered.label == "Always allow scripts on shop.example"
    rule = remembered.permission_updates[0].payload
    assert rule["matcher"] == site_rule("allow")["matcher"]

    rules = [site_rule("allow")]
    assert (await decide(run_js(), tmp_path, rules)).behavior == CommandDecision.ALLOW
    other = run_js(site="https://bank.example")
    assert (await decide(other, tmp_path, rules)).behavior == CommandDecision.ASK
    blocked = await decide(run_js(), tmp_path, [site_rule("deny")])
    assert blocked.behavior == CommandDecision.DENY


async def test_ordinary_browser_actions_never_ask(tmp_path: Path) -> None:
    for command in ("click", "batch", "open"):
        decision = await decide({"command": command}, tmp_path)
        assert decision.behavior == CommandDecision.ALLOW


async def test_unapproved_code_is_deferred_for_approval() -> None:
    tool = BrowsingTool()
    ctx = SimpleNamespace(tool_call_approved=False)
    with pytest.raises(ApprovalRequired):
        await tool.forward(ctx, "run_js", ["return 1"], SITE)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
@pytest.mark.parametrize(
    "code",
    [
        "document.title = 'ran'; return 1",
        # Closes the wrapper early to add its own top-level statements.
        "})(), 0]); })(); document.title = 'ran'; "
        "(async () => { await Promise.race([(async () => {",
    ],
)
def test_code_never_runs_on_another_site(code: str) -> None:
    program = f"""
const vm = require('vm');
const page = {{location: {{origin: 'https://bank.example'}}, document: {{title: ''}},
  setTimeout, Promise, JSON, String, Error}};
try {{ vm.runInNewContext({json.dumps(script_expression(SITE, code))}, page); }}
catch (error) {{ page.error = String(error.message); }}
setTimeout(() => console.log(JSON.stringify(page.document.title)), 20);
"""
    title = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, check=True
    ).stdout
    assert json.loads(title) == ""


def test_a_wrong_site_tells_the_agent_where_the_page_is() -> None:
    result = script_error(SITE, "Error: suzent-wrong-site:https://bank.example")
    assert not result.success
    assert "on https://bank.example, not https://shop.example" in result.message


def test_batch_steps_keep_spaces_in_typed_values() -> None:
    assert parse_batch_step("fill @g1e2 Ada  Lovelace") == (
        "fill",
        ["@g1e2", "Ada  Lovelace"],
    )
    assert parse_batch_step("scroll 0 400") == ("scroll", ["0", "400"])
    for step in ("run_js return 1", "batch click @g1e1", "snapshot"):
        with pytest.raises(ValueError):
            parse_batch_step(step)


async def test_batch_stops_at_the_first_failed_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = BrowsingTool()
    calls: list[str] = []

    async def run(command: str, arguments=None, site=None):
        calls.append(" ".join([command, *(arguments or [])]))
        if command == "click":
            return tool_module.ToolResult.error_result(
                tool_module.ToolErrorCode.INVALID_ARGUMENT, "Ref expired."
            )
        if command == "snapshot":
            return tool_module.ToolResult.success_result("[Page: Form]")
        return tool_module.ToolResult.success_result(f"{command} completed.")

    monkeypatch.setattr(tool, "_run", run)
    monkeypatch.setattr(tool_module, "OBSERVE_DELAY", 0)
    result = await tool._execute(
        "batch", ["fill @g1e0 Ada", "click @g1e1", "fill @g1e2 x"]
    )
    assert calls == ["fill @g1e0 Ada", "click @g1e1", "snapshot"]
    assert not result.success
    assert result.message.startswith("Step 2 (click) failed: Ref expired.")
    assert "[Page: Form]" in result.message


async def test_an_agent_run_pauses_for_code_and_runs_it_once_approved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from suzent.tools.registry import _make_tool

    ran: list[tuple] = []

    async def execute(self, command, arguments=None, site=None):
        ran.append((command, arguments, site))
        return tool_module.ToolResult.success_result("run_js returned: 1")

    monkeypatch.setattr(BrowsingTool, "_execute", execute)
    args = run_js()

    def model(messages, info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("browser_action", args, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(
        FunctionModel(model),
        tools=[_make_tool(BrowsingTool)],
        output_type=[str, DeferredToolRequests],
    )
    paused = await agent.run("go")
    assert isinstance(paused.output, DeferredToolRequests)
    assert [call.tool_name for call in paused.output.approvals] == ["browser_action"]
    assert ran == []

    approved = DeferredToolResults(approvals={"c1": True})
    await agent.run(
        message_history=paused.all_messages(), deferred_tool_results=approved
    )
    assert ran == [("run_js", ["return 1"], SITE)]
