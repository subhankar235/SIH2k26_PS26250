"""Tests for tactical rationale synthesizer and templates."""

import pytest
from llm.templates import render_agent_rationale
from llm.synthesizer import TacticalRationaleSynthesizer


def test_render_agent_rationale_templates():
    context = {
        "mission_id": "M-Ammo-01",
        "airframe_id": "C130-Alpha",
        "corridor_id": "Corr-North-Direct",
        "reason": "Hostile SAM radar active",
        "alternative": "Corr-North-Detour",
    }

    # Proposal
    prop = render_agent_rationale("FleetAgent", "PROPOSAL", context)
    assert "Evaluating allocation matrix" in prop
    assert "M-Ammo-01" in prop

    # Accept
    acc = render_agent_rationale("FleetAgent", "ACCEPT", context)
    assert "AFFIRMATIVE" in acc

    # Objection
    obj = render_agent_rationale("ThreatAgent", "OBJECTION", context)
    assert "VETO / OBJECTION" in obj
    assert "Hostile SAM radar active" in obj

    # Counter-bid
    counter = render_agent_rationale("ThreatAgent", "COUNTER_BID", context)
    assert "COUNTER-PROPOSAL" in counter
    assert "Corr-North-Detour" in counter


@pytest.mark.asyncio
async def test_synthesizer_fallback_when_disabled():
    synthesizer = TacticalRationaleSynthesizer(enabled=False)
    context = {"mission_id": "M-101", "airframe_id": "IL76-Bravo"}
    msg = await synthesizer.synthesize_rationale("Melchior-Fleet", "ACCEPT", context)
    assert "AFFIRMATIVE" in msg
    assert "[Melchior-Fleet]" in msg

