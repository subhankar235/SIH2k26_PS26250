"""Base class and common types for MAGI domain agents."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from solver.model import Mission, Airframe, Crew, Corridor


@dataclass
class AgentVote:
    agent_name: str
    approved: bool
    confidence: float = 1.0
    rationale: str = ""
    objection_code: Optional[str] = None
    suggested_alternative: Optional[Dict[str, Any]] = None


class BaseMagiAgent(ABC):
    """Abstract base class for all MAGI domain specialist agents."""

    def __init__(self, name: str, domain: str):
        self.name = name
        self.domain = domain
        self.state: Dict[str, Any] = {}

    def update_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Update the agent's real-time domain knowledge state."""
        self.state.update(telemetry)

    @abstractmethod
    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        """Evaluate a candidate assignment from the agent's domain perspective."""
        pass

