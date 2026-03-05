"""Central manager for tool approvals across all interfaces."""

from typing import Dict, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from suzent.core.agent_deps import AgentDeps

# Type hint using string to avoid circular import if AgentDeps imports this
# The actual active_deps dictionary holds AgentDeps instances
active_deps: Dict[str, "AgentDeps"] = {}


def get_all_pending_approvals() -> List[dict]:
    """Return a flattened list of all pending tool approvals."""
    pending = []
    for chat_id, deps in active_deps.items():
        for req_id, req_data in deps.pending_approvals.items():
            pending.append(
                {
                    "chat_id": chat_id,
                    "request_id": req_id,
                    "tool_name": req_data.get("tool_name"),
                    "args": req_data.get("args", {}),
                }
            )
    return pending


def resolve_approval(
    request_id: str,
    approved: bool,
    chat_id: Optional[str] = None,
    remember: Optional[str] = None,
) -> bool:
    """
    Resolve a pending approval. If chat_id is missing, search all active sessions (global resolve).
    """
    target_chats = [chat_id] if chat_id else list(active_deps.keys())

    for cid in target_chats:
        deps = active_deps.get(cid)
        if not deps:
            continue

        req = deps.pending_approvals.get(request_id)
        if req:
            req["approved"] = approved
            req["remember"] = remember
            evt = req.get("event")
            if evt:
                evt.set()
            return True
    return False
