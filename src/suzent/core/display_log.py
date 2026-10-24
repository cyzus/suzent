"""Display records are captured from stream events, independently of model context."""

from copy import deepcopy
from typing import Any


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
