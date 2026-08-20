"""A2A (Agent2Agent) protocol support — open federation for the Suzent mesh.

The Suzent-native peer channel (``suzent.nodes``) stays the trusted fast path
between two Suzent installs: it carries attachments, pairing grants, and mDNS
discovery. A2A is the open door — it lets this agent talk to, and be driven by,
any agent that speaks the standard, regardless of who built it.

Deliberately *not* part of this: the node protocol. Nodes advertise a
transparent, enumerable capability manifest (``camera.snap``), while A2A's model
is opaque execution. Collapsing the two would lose the manifest.
"""

from suzent.a2a.card import build_agent_card, card_metadata
from suzent.a2a.tasks import TaskStore, get_task_store
from suzent.a2a.types import PROTOCOL_VERSION, Message, Task, TaskState

__all__ = [
    "PROTOCOL_VERSION",
    "Message",
    "Task",
    "TaskState",
    "TaskStore",
    "build_agent_card",
    "card_metadata",
    "get_task_store",
]
