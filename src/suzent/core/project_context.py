"""Resolve the project a chat belongs to.

The goal tool, the three task tools and the ``/goal`` command all key their
work on the project behind the current chat, and each carried its own copy of
this lookup. They have to agree: a chat that resolves to a project for the task
tools but not for ``/goal`` would quietly split a goal from the tasks under it.

The database import is deferred so importing this module stays cheap for
callers that only want the function.
"""

from __future__ import annotations

from typing import Optional


def resolve_project_id(chat_id: Optional[str]) -> Optional[str]:
    """Return the project linked to *chat_id*, or None when there is no link.

    A missing ``chat_id`` is not an error here -- ACP and sub-agent runs have no
    chat -- so it resolves to None like an unlinked chat does.
    """
    if not chat_id:
        return None

    from suzent.database import get_database

    return get_database().get_chat_project_id(chat_id)
