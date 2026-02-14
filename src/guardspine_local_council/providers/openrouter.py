"""OpenRouter provider -- access 500+ models via OpenAI-compatible API."""

import json
import os
import uuid

import httpx

from ..types import ReviewVote


class OpenRouterProvider:
    """Calls OpenRouter's chat completions endpoint to produce a ReviewVote.

    OpenRouter is OpenAI-compatible, so the request/response schema matches.
    Any model available on OpenRouter can be used (e.g. "meta-llama/llama-3-70b",
    "anthropic/claude-3.5-sonnet", "google/gemini-pro", "openrouter/auto").
    """

    def __init__(
        self,
        model: str = "openrouter/auto",
        api_key: str | None = None,
        site_url: str | None = None,
        site_name: str | None = None,
        reviewer_id: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.site_url = site_url or ""
        self.site_name = site_name or "guardspine-council"
        self.reviewer_id = reviewer_id or f"openrouter-{model.split('/')[-1][:20]}-{uuid.uuid4().hex[:6]}"
        self.timeout = timeout

    async def review(self, prompt: str) -> ReviewVote:
        """Send prompt to OpenRouter and return a structured ReviewVote."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a code auditor. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
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
