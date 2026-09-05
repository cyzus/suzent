"""One-shot native messaging helper; stdout is reserved for framed JSON."""

import json
import struct
import sys
from pathlib import Path
from typing import BinaryIO


def serve(port_file: Path, source: BinaryIO, target: BinaryIO) -> None:
    header = source.read(4)
    if len(header) != 4:
        return
    length = struct.unpack("=I", header)[0]
    if not 0 < length <= 4096:
        return
    try:
        request = json.loads(source.read(length))
        if request != {"action": "endpoint"}:
            return
        port = int(port_file.read_text(encoding="utf-8").strip())
        if not 1 <= port <= 65535:
            return
        payload = json.dumps(
            {"url": f"ws://127.0.0.1:{port}/ws/browser-extension"}
        ).encode()
        target.write(struct.pack("=I", len(payload)) + payload)
        target.flush()
    except (OSError, ValueError):
        return


if __name__ == "__main__":
    if sys.platform == "win32":
        import msvcrt
        import os

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    serve(Path(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer)
