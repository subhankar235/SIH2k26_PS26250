"""Types and message definitions for the MAGI multi-agent negotiation protocol."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime, timezone


@dataclass
class NegotiationMessage:
    agent_name: str
    message_type: str  # "PROPOSAL", "ACCEPT", "OBJECTION", "COUNTER_BID", "VERDICT"
    mission_id: str
    round_number: int
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "message_type": self.message_type,
            "mission_id": self.mission_id,
            "round_number": self.round_number,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

