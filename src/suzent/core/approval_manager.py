"""
Approval Manager: Unified human-in-the-loop session tracking.

Extracted from social_brain.py so that both social and desktop approval
flows can reuse the same session model.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from suzent.core.stream_parser import ApprovalRequest


@dataclass
class PendingApprovalSession:
    """Tracks a batch of tool approvals for a single agent turn."""

    requests: List[ApprovalRequest]
    decisions: Dict[str, bool] = field(default_factory=dict)  # request_id -> approved
    remember_decisions: Dict[str, bool] = field(
        default_factory=dict
    )  # request_id -> remember
    config_override: Optional[Dict] = None
    platform: str = ""
    target_id: str = ""
    sender_id: str = ""  # original requester -- only they may approve in groups

    @property
    def current_index(self) -> int:
        return len(self.decisions)

    @property
    def total(self) -> int:
        return len(self.requests)

    @property
    def all_decided(self) -> bool:
        return self.current_index >= self.total

    @property
    def next_request(self) -> Optional[ApprovalRequest]:
        if self.all_decided:
            return None
        return self.requests[self.current_index]

    def record(self, approved: bool, remember: bool = False):
        """Record a decision for the current request."""
        req = self.next_request
        if req:
            self.decisions[req.request_id] = approved
            self.remember_decisions[req.request_id] = remember

    def to_resume_approvals(self) -> List[Dict]:
        """Build the resume_approvals payload for ChatProcessor.

        Includes ``remember``, ``tool_name``, and ``args`` so ChatProcessor can
        apply the standard permission pathway (command-level rules, global persist).
        """
        return [
            {
                "request_id": req.request_id,
                "tool_call_id": req.tool_call_id,
                "approved": self.decisions[req.request_id],
                "remember": "session"
                if self.remember_decisions.get(req.request_id)
                else "",
                "tool_name": req.tool_name,
                "args": req.args,
            }
            for req in self.requests
        ]
