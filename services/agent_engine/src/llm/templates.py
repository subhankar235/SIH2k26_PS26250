"""Deterministic tactical rationale templates for MAGI agents."""

from typing import Dict, Any


def render_agent_rationale(agent_name: str, message_type: str, context: Dict[str, Any]) -> str:
    """Generate tactical, structured dialogue in the style of MAGI consensus."""
    mission_id = context.get("mission_id", "UNKNOWN")
    airframe_id = context.get("airframe_id", "AIRCRAFT")
    corridor_id = context.get("corridor_id", "CORRIDOR")
    reason = context.get("reason", "")

    if message_type == "PROPOSAL":
        return f"[{agent_name}] Evaluating allocation matrix for Mission {mission_id}: Assigned Airframe {airframe_id} via Corridor {corridor_id}."

    if message_type == "ACCEPT":
        return f"[{agent_name}] AFFIRMATIVE. Tactical parameters verified for Mission {mission_id}. Operational safety envelope intact."

    if message_type == "OBJECTION":
        return f"[{agent_name}] VETO / OBJECTION on Mission {mission_id}. Breach detected: {reason}."

    if message_type == "COUNTER_BID":
        alt = context.get("alternative", "detour route")
        return f"[{agent_name}] COUNTER-PROPOSAL: Divert Mission {mission_id} to {alt} to preserve operational equilibrium."

    if message_type == "VERDICT":
        status = context.get("status", "CONSENSUS_REACHED")
        return f"[COORDINATOR // MAGI-SYSTEM] Deliberation complete. Status: {status}. Dispatching flight orders."

    return f"[{agent_name}] {message_type}: Tactical parameters processed."

