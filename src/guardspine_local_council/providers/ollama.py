"""Ollama provider for local model inference."""

from __future__ import annotations

import json
import uuid

import httpx

from ..types import ReviewVote


class OllamaProvider:
    """Calls a local Ollama instance to produce a ReviewVote."""

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        reviewer_id: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.reviewer_id = reviewer_id or f"ollama-{model}-{uuid.uuid4().hex[:6]}"

    async def review(self, prompt: str) -> ReviewVote:
        """Send prompt to Ollama and return a structured ReviewVote."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()

        raw_text = body.get("response", "")
        return self._parse_response(raw_text)

    def _parse_response(self, text: str) -> ReviewVote:
        """Extract decision, confidence, rationale, findings from model output.

        Expects JSON with keys: decision, confidence, rationale, findings.
        Falls back to abstain on parse failure.
        """
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return ReviewVote(
                reviewer_id=self.reviewer_id,
                decision="abstain",
                confidence=0.0,
                rationale=f"Failed to parse model output: {text[:200]}",
                findings=[],
            )

        decision = data.get("decision", "abstain")
        if decision not in ("approve", "reject", "abstain"):
            decision = "abstain"

        confidence = data.get("confidence", 0.0)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        rationale = str(data.get("rationale", ""))
        findings = data.get("findings", [])
        if not isinstance(findings, list):
            findings = []

        return ReviewVote(
            reviewer_id=self.reviewer_id,
            decision=decision,
            confidence=confidence,
            rationale=rationale,
            findings=findings,
        )
