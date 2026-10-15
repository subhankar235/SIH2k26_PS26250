"""Negotiation module exports."""

from .protocol import NegotiationMessage
from .coordinator import MagiCoordinator

__all__ = [
    "NegotiationMessage",
    "MagiCoordinator",
]

