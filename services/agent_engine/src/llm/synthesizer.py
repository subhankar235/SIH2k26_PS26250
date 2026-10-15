"""Tactical Rationale Synthesizer with local SLM and deterministic fallback."""

import os
import httpx
from typing import Dict, Any, Optional
from .templates import render_agent_rationale


class TacticalRationaleSynthesizer:
    """Generates tactical MAGI agent dialogues with optional local Ollama assistance."""

    def __init__(
        self,
        ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        model_name: str = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
        enabled: bool = os.getenv("ENABLE_LOCAL_SLM", "false").lower() in ("true", "1", "yes"),
        timeout_seconds: float = 2.0
    ):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds

    async def synthesize_rationale(
        self,
        agent_name: str,
        message_type: str,
        context: Dict[str, Any]
    ) -> str:
        """Synthesize tactical reasoning, falling back to deterministic templates."""
        fallback = render_agent_rationale(agent_name, message_type, context)

        if not self.enabled:
            return fallback

        prompt = (
            f"You are {agent_name}, an autonomous defence logistics decision agent in a MAGI supercomputing network. "
            f"Generate a single, concise (1-2 sentences), highly tactical military dispatch message for {message_type}. "
            f"Context: {context}. Message:"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model_name,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                if response.status_code == 200:
                    text = response.json().get("response", "").strip()
                    if text:
                        return f"[{agent_name}] {text}"
        except Exception:
            # Graceful instant fallback to deterministic template
            pass

        return fallback

