"""Anthropic provider for Claude model inference."""

import json
import os
import uuid

import httpx

from ..types import ReviewVote


class AnthropicProvider:
    """Calls the Anthropic Messages API to produce a ReviewVote."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 4096,
        reviewer_id: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.reviewer_id = reviewer_id or f"anthropic-{model.split('-')[0]}-{uuid.uuid4().hex[:6]}"
        self.timeout = timeout

    async def review(self, prompt: str) -> ReviewVote:
        """Send prompt to Anthropic Messages API and return a structured ReviewVote."""
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": "You are a code auditor. Respond with valid JSON only.",
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()

        # Extract text from content blocks
        raw_text = ""
        for block in body.get("content", []):
            if block.get("type") == "text":
                raw_text += block.get("text", "")

        return self._parse_response(raw_text)

    def _parse_response(self, text: str) -> ReviewVote:
        # Strip markdown code fences if model wraps JSON in them
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
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
