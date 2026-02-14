"""OpenAI provider for cloud model inference."""

import json
import os
import uuid

import httpx

from ..types import ReviewVote


class OpenAIProvider:
    """Calls the OpenAI Chat Completions API to produce a ReviewVote."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        reviewer_id: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.reviewer_id = reviewer_id or f"openai-{model}-{uuid.uuid4().hex[:6]}"
        self.timeout = timeout

    async def review(self, prompt: str) -> ReviewVote:
        """Send prompt to OpenAI and return a structured ReviewVote."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a code auditor. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()

        raw_text = body["choices"][0]["message"]["content"]
        return self._parse_response(raw_text)

    def _parse_response(self, text: str) -> ReviewVote:
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
