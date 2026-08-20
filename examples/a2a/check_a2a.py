#!/usr/bin/env python3
"""
Check whether an A2A agent is working — yours, or anybody else's.

Fetches the Agent Card, then probes the JSON-RPC surface and reports what the
agent actually supports. Nothing here is Suzent-specific: point it at any A2A
implementation.

    python check_a2a.py                          # this machine, default port
    python check_a2a.py http://100.87.231.85:25314
    python check_a2a.py https://agent.example.com --token "$TOKEN"

Only the last probe (--live) runs a real task, which costs a model call on the
far end. Everything else is free and needs no API key, so a failing model
configuration can't be mistaken for a broken protocol.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

import httpx

CARD_PATH = "/.well-known/agent-card.json"
OK, BAD, INFO = "  [ok]  ", "  [!!]  ", "  [--]  "


def _rpc(method: str, params: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": method,
        "params": params,
    }


async def probe(base_url: str, token: str, live: bool) -> int:
    base = base_url.rstrip("/")
    if "://" not in base:
        base = f"http://{base}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    failures = 0

    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        # ─── 1. Discovery ────────────────────────────────────────────
        print(f"\nAgent card  {base}{CARD_PATH}")
        try:
            res = await client.get(f"{base}{CARD_PATH}")
        except httpx.HTTPError as exc:
            print(f"{BAD}unreachable: {type(exc).__name__}")
            print("\n  Is the server running, and reachable from here?")
            return 1

        if res.status_code == 404:
            print(f"{BAD}404 - this agent has not published a card")
            print("\n  In Suzent: Settings -> Mesh -> This device -> toggle on.")
            return 1
        if res.status_code != 200:
            print(f"{BAD}HTTP {res.status_code}")
            return 1

        card = res.json()
        rpc_url = str(card.get("url") or f"{base}/a2a/v1")
        print(f"{OK}{card.get('name')} - {card.get('description', '')[:60]}")
        print(
            f"{INFO}protocol {card.get('protocolVersion')}  "
            f"transport {card.get('preferredTransport')}"
        )
        print(
            f"{INFO}streaming={card.get('capabilities', {}).get('streaming')}  "
            f"skills={[s.get('id') for s in card.get('skills', [])]}"
        )
        print(
            f"{INFO}auth: {list((card.get('securitySchemes') or {}).keys()) or 'none'}"
        )

        # ─── 2. The RPC surface ──────────────────────────────────────
        print(f"\nJSON-RPC  {rpc_url}")

        async def call(method: str, params: dict) -> dict | None:
            try:
                r = await client.post(
                    rpc_url, headers=headers, json=_rpc(method, params)
                )
            except httpx.HTTPError as exc:
                print(f"{BAD}{method}: unreachable ({type(exc).__name__})")
                return None
            if r.status_code == 401:
                print(f"{BAD}{method}: HTTP 401 - needs a token (pass --token)")
                return None
            if r.status_code >= 400:
                print(f"{BAD}{method}: HTTP {r.status_code}")
                return None
            try:
                return r.json()
            except ValueError:
                print(f"{BAD}{method}: response was not JSON")
                return None

        # A task id that cannot exist: a conforming agent answers -32001.
        got = await call("tasks/get", {"id": "definitely-not-a-real-task"})
        if got is None:
            failures += 1
        elif got.get("error", {}).get("code") == -32001:
            print(f"{OK}tasks/get     implemented (correctly reports task not found)")
        else:
            print(f"{BAD}tasks/get     unexpected: {json.dumps(got)[:100]}")
            failures += 1

        got = await call("tasks/cancel", {"id": "definitely-not-a-real-task"})
        if got is None:
            failures += 1
        elif got.get("error", {}).get("code") in (-32001, -32002):
            print(f"{OK}tasks/cancel  implemented")
        else:
            print(f"{BAD}tasks/cancel  unexpected: {json.dumps(got)[:100]}")
            failures += 1

        # An empty message must be rejected as invalid params, not accepted.
        got = await call(
            "message/send",
            {
                "message": {
                    "kind": "message",
                    "messageId": "probe",
                    "role": "user",
                    "parts": [],
                }
            },
        )
        if got is None:
            failures += 1
        elif got.get("error", {}).get("code") == -32602:
            print(f"{OK}message/send  implemented (validates its input)")
        else:
            print(
                f"{BAD}message/send  should reject an empty message: "
                f"{json.dumps(got)[:100]}"
            )
            failures += 1

        got = await call("this/method/does/not/exist", {})
        if got is None:
            failures += 1
        elif got.get("error", {}).get("code") == -32601:
            print(f"{OK}unknown method rejected (-32601)")
        else:
            print(f"{BAD}unknown method should return -32601")
            failures += 1

        # ─── 3. A real task (costs a model call) ─────────────────────
        if live:
            print("\nLive task  (runs a real turn on the far end)")
            got = await call(
                "message/send",
                {
                    "message": {
                        "kind": "message",
                        "messageId": uuid.uuid4().hex,
                        "role": "user",
                        "parts": [
                            {"kind": "text", "text": "Reply with exactly: MESH OK"}
                        ],
                    }
                },
            )
            if got is None:
                failures += 1
            elif "error" in got:
                print(f"{BAD}{json.dumps(got['error'])[:160]}")
                failures += 1
            else:
                task = got.get("result", {})
                state = task.get("status", {}).get("state")
                reply = " ".join(
                    p.get("text", "")
                    for p in task.get("status", {}).get("message", {}).get("parts", [])
                )
                marker = OK if state == "completed" else BAD
                print(f"{marker}state={state}  reply={reply[:80]!r}")
                if state != "completed":
                    failures += 1

    print()
    if failures:
        print(f"{failures} check(s) failed.")
    else:
        print("All checks passed - this agent speaks A2A.")
        if not live:
            print("Re-run with --live to have it actually perform a task.")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe an A2A agent")
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:25314")
    parser.add_argument(
        "--token", default="", help="bearer token, if the agent needs one"
    )
    parser.add_argument("--live", action="store_true", help="also run a real task")
    args = parser.parse_args()
    sys.exit(asyncio.run(probe(args.url, args.token, args.live)))


if __name__ == "__main__":
    main()
