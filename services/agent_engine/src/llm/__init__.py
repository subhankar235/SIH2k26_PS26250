"""LLM and explanation module exports."""

from .templates import render_agent_rationale
from .synthesizer import TacticalRationaleSynthesizer

__all__ = [
    "render_agent_rationale",
    "TacticalRationaleSynthesizer",
]

