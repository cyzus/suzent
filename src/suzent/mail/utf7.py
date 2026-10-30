"""IMAP modified UTF-7 (RFC 3501 §5.1.3), the encoding of non-ASCII folder names.

Chinese mailboxes name their folders this way: 草稿箱 arrives as ``&g0l6P3ux-``.
"""

from __future__ import annotations

import base64


def imap_utf7_decode(name: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(name):
        char = name[i]
        if char != "&":
            out.append(char)
            i += 1
            continue
        end = name.find("-", i)
        if end == -1:
            out.append(name[i:])
            break
        chunk = name[i + 1 : end]
        if not chunk:
            out.append("&")
        else:
            b64 = chunk.replace(",", "/")
            b64 += "=" * (-len(b64) % 4)
            try:
                out.append(base64.b64decode(b64).decode("utf-16-be"))
            except (ValueError, UnicodeDecodeError):
                out.append(name[i : end + 1])
        i = end + 1
    return "".join(out)


def imap_utf7_encode(name: str) -> str:
    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            raw = "".join(pending).encode("utf-16-be")
            out.append(
                "&" + base64.b64encode(raw).decode().rstrip("=").replace("/", ",") + "-"
            )
            pending.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            out.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(out)
