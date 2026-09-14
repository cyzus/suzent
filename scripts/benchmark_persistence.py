"""Measure synthetic chat persistence and event-loop stalls in a temporary database.

Run with the project's Python environment and PYTHONPATH pointing at the source
revision to measure. No existing database or conversation is read.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch


async def measure(turns: list[int], repeats: int, directory: Path) -> list[dict]:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )
    from suzent.core.chat_processor import ChatProcessor, _rebuild_display_messages
    from suzent.database import ChatDatabase
    from suzent.streaming import _persist_draft_display_message

    database = ChatDatabase(str(directory / "benchmark.db"))
    results = []
    try:
        with (
            patch("suzent.core.chat_processor.get_database", return_value=database),
            patch("suzent.database.get_database", return_value=database),
        ):
            processor = ChatProcessor()
            for count in turns:
                messages = []
                for index in range(count):
                    messages.extend(
                        [
                            ModelRequest(
                                parts=[
                                    UserPromptPart(f"Question {index} " + "x" * 1024)
                                ]
                            ),
                            ModelResponse(
                                parts=[TextPart(f"Answer {index} " + "y" * 1024)]
                            ),
                        ]
                    )
                display = _rebuild_display_messages(messages, model_id="benchmark")
                chat_id = database.create_chat(
                    title="Synthetic benchmark", messages=display, config={}
                )
                samples = {
                    "snapshot_ms": [],
                    "draft_ms": [],
                    "finalize_ms": [],
                    "loop_stall_ms": [],
                }
                for _ in range(repeats):
                    started = time.perf_counter()
                    revision = await processor._persist_agent_state_snapshot(
                        chat_id, messages, "benchmark", []
                    )
                    samples["snapshot_ms"].append(
                        (time.perf_counter() - started) * 1000
                    )
                    started = time.perf_counter()
                    await asyncio.to_thread(
                        _persist_draft_display_message,
                        chat_id,
                        "benchmark-run",
                        [{"type": "text", "text": "partial"}],
                        "partial",
                    )
                    samples["draft_ms"].append((time.perf_counter() - started) * 1000)
                    lags = []

                    async def heartbeat() -> None:
                        while True:
                            tick = time.perf_counter()
                            await asyncio.sleep(0.001)
                            lags.append(
                                max(0, time.perf_counter() - tick - 0.001) * 1000
                            )

                    monitor = asyncio.create_task(heartbeat())
                    await asyncio.sleep(0)
                    started = time.perf_counter()
                    await processor._persist_state(
                        chat_id,
                        messages,
                        "benchmark",
                        [],
                        "question",
                        "answer",
                        expected_revision=revision,
                    )
                    samples["finalize_ms"].append(
                        (time.perf_counter() - started) * 1000
                    )
                    await asyncio.sleep(0.002)
                    monitor.cancel()
                    try:
                        await monitor
                    except asyncio.CancelledError:
                        pass
                    samples["loop_stall_ms"].append(max(lags, default=0))
                    saved = database.get_chat(chat_id)
                    assert saved.finalized_revision == revision
                    assert len(saved.messages) == count * 2
                results.append(
                    {
                        "turns": count,
                        "display_kib": round(
                            len(json.dumps(display).encode()) / 1024, 1
                        ),
                        "repeats": repeats,
                        **{
                            key: round(statistics.median(values), 2)
                            for key, values in samples.items()
                        },
                    }
                )
    finally:
        database.engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    with tempfile.TemporaryDirectory(prefix="suzent-persistence-benchmark-") as temp:
        directory = Path(temp)
        os.environ["SUZENT_DATA_DIR"] = str(directory)
        os.environ["CHATS_DB_PATH"] = str(directory / "default.db")
        os.environ["SUZENT_USER_CONFIG_PATH"] = str(directory / "config.yaml")
        rows = asyncio.run(measure([10, 100, 500], args.repeats, directory))
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
