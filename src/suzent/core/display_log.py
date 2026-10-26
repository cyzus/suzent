"""Display records are captured from stream events, independently of model context."""

from copy import deepcopy
from collections.abc import Iterable
from datetime import datetime
from typing import Any


def recover_logged_run_timing(
    messages: list[dict[str, Any]], events: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Estimate legacy run ends from their first finalized append, never later edits."""
    missing = {
        message["_streaming_run_id"]
        for message in messages
        if message.get("role") == "assistant"
        and message.get("_streaming_run_id")
        and not message.get("_streaming_draft")
        and not message.get("run_finished_at")
        and not message.get("run_timings")
    }
    if not missing:
        return messages
    ends: dict[str, str] = {}
    for event in events:
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        rows = (
            [data]
            if event.get("type") == "message.append"
            else data.get("insert", [])
            if event.get("type") == "messages.splice"
            else []
        )
        for row in rows:
            run_id = row.get("_streaming_run_id")
            if (
                run_id in missing
                and not row.get("_streaming_draft")
                and event.get("ts")
            ):
                ends.setdefault(run_id, event["ts"])
        if len(ends) == len(missing):
            break
    result = []
    for message in messages:
        run_id = message.get("_streaming_run_id")
        start = message.get("run_started_at") or message.get("timestamp")
        end = ends.get(run_id) if run_id in missing else None
        if start and end:
            try:
                started = datetime.fromisoformat(start)
                finished = datetime.fromisoformat(end)
                valid = (
                    started.tzinfo is not None
                    and finished.tzinfo is not None
                    and finished >= started
                )
            except (ValueError, TypeError):
                valid = False
            if valid:
                message = {
                    **message,
                    "run_started_at": start,
                    "run_finished_at": end,
                    "run_timing_source": "log_append",
                }
        result.append(message)
    return result


def merge_streamed_message(
    messages: list[dict[str, Any]], message: dict[str, Any]
) -> list[dict[str, Any]]:
    """Upsert one run's output without inferring ownership from text or position."""
    run_id = message["_streaming_run_id"]
    result = list(messages)
    message = deepcopy(message)
    resumed_ids = set(message.get("_resumed_tool_call_ids") or [])
    retained_parts = []
    for part in message.get("parts") or []:
        matched = False
        if part.get("type") == "tool" and part.get("toolCallId") in resumed_ids:
            for index in range(len(result) - 1, -1, -1):
                row = result[index]
                if row.get("_streaming_run_id") == run_id:
                    continue
                for part_index, previous in enumerate(row.get("parts") or []):
                    if previous.get("type") != "tool" or previous.get(
                        "toolCallId"
                    ) != part.get("toolCallId"):
                        continue
                    row = deepcopy(row)
                    updates = {
                        key: value
                        for key, value in part.items()
                        if not (key == "args" and not value)
                        and not (key == "toolName" and value == "unknown")
                    }
                    row["parts"][part_index] = {**previous, **updates}
                    # A tool-only resume may not produce a new display row.
                    # Keep its timing on the updated card so that work survives.
                    if message.get("run_started_at") and message.get("run_finished_at"):
                        timings = {}
                        for source in (row, message):
                            runs = source.get("run_timings") or []
                            if (
                                not runs
                                and source.get("run_started_at")
                                and source.get("run_finished_at")
                            ):
                                runs = [
                                    {
                                        "run_id": source.get("_streaming_run_id"),
                                        "started_at": source["run_started_at"],
                                        "finished_at": source["run_finished_at"],
                                        **(
                                            {
                                                "active_seconds": source[
                                                    "run_active_seconds"
                                                ]
                                            }
                                            if "run_active_seconds" in source
                                            else {}
                                        ),
                                    }
                                ]
                            for timing in runs:
                                if timing.get("run_id"):
                                    timings[timing["run_id"]] = timing
                        row["run_timings"] = list(timings.values())
                    result[index] = row
                    matched = True
                    break
                if matched:
                    break
        if not matched:
            retained_parts.append(part)
    if resumed_ids:
        message["parts"] = retained_parts
    for index, existing in enumerate(result):
        if existing.get("_streaming_run_id") == run_id:
            # A delayed draft must never resurrect an already finalized run.
            if message.get("_streaming_draft") and not existing.get("_streaming_draft"):
                return result
            result[index] = {**existing, **deepcopy(message)}
            if not message.get("_streaming_draft"):
                result[index].pop("_streaming_draft", None)
            return result
    if not resumed_ids or retained_parts or message.get("content"):
        result.append(deepcopy(message))
    return result
