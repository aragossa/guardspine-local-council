"""Tests for LocalCouncil."""

import asyncio
import unittest

from guardspine_local_council.council import LocalCouncil
from guardspine_local_council.types import ReviewRequest, ReviewVote


class FakeProvider:
    """A fake provider that returns a predetermined vote."""

    def __init__(self, reviewer_id: str, decision: str, confidence: float):
        self.reviewer_id = reviewer_id
        self._decision = decision
        self._confidence = confidence

    async def review(self, prompt: str) -> ReviewVote:
        return ReviewVote(
            reviewer_id=self.reviewer_id,
            decision=self._decision,
            confidence=self._confidence,
            rationale="fake rationale",
            findings=[],
        )


class ErrorProvider:
    """A provider that always raises."""

    def __init__(self, reviewer_id: str = "error-provider"):
        self.reviewer_id = reviewer_id

    async def review(self, prompt: str) -> ReviewVote:
        raise RuntimeError("connection failed")


class TestLocalCouncil(unittest.TestCase):
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_unanimous_approve(self):
        providers = [
            FakeProvider("r1", "approve", 0.9),
            FakeProvider("r2", "approve", 0.8),
            FakeProvider("r3", "approve", 0.7),
        ]
        council = LocalCouncil(providers, quorum=3)
        req = ReviewRequest("art-1", "code", "print('hello')")
        result = self._run(council.review(req))

        self.assertEqual(result.consensus_decision, "approve")
        self.assertTrue(result.quorum_met)
        self.assertEqual(len(result.votes), 3)
        self.assertEqual(len(result.dissenting_opinions), 0)

    def test_quorum_not_met(self):
        providers = [
            FakeProvider("r1", "approve", 0.9),
            FakeProvider("r2", "abstain", 0.0),
            FakeProvider("r3", "abstain", 0.0),
        ]
        council = LocalCouncil(providers, quorum=3)
        req = ReviewRequest("art-2", "code", "x = 1")
        result = self._run(council.review(req))

        self.assertFalse(result.quorum_met)

    def test_provider_error_becomes_abstain(self):
        providers = [
            FakeProvider("r1", "approve", 0.9),
            FakeProvider("r2", "approve", 0.8),
            ErrorProvider("r3"),
        ]
        council = LocalCouncil(providers, quorum=2)
        req = ReviewRequest("art-3", "code", "y = 2")
        result = self._run(council.review(req))

        self.assertEqual(len(result.votes), 3)
        error_vote = [v for v in result.votes if v.reviewer_id == "r3"][0]
        self.assertEqual(error_vote.decision, "abstain")

    def test_below_consensus_threshold(self):
        providers = [
            FakeProvider("r1", "approve", 0.4),
            FakeProvider("r2", "reject", 0.3),
            FakeProvider("r3", "abstain", 0.3),
        ]
        council = LocalCouncil(providers, quorum=2, consensus_threshold=0.8)
        req = ReviewRequest("art-4", "code", "z = 3")
        result = self._run(council.review(req))

        self.assertEqual(result.consensus_decision, "abstain")

    def test_build_prompt_includes_content(self):
        providers = [FakeProvider("r1", "approve", 0.9)]
        council = LocalCouncil(providers)
        req = ReviewRequest("art-5", "config", "key: value", context={"env": "prod"}, risk_tier_hint="high")
        prompt = council._build_prompt(req)

        self.assertIn("art-5", prompt)
        self.assertIn("config", prompt)
        self.assertIn("key: value", prompt)
        self.assertIn("prod", prompt)
        self.assertIn("high", prompt)


if __name__ == "__main__":
    unittest.main()
