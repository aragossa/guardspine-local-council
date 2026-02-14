"""Vote aggregation for council decisions."""

from .types import ReviewVote


class SimpleAggregator:
    """Majority vote aggregator with confidence weighting."""

    def aggregate(self, votes: list[ReviewVote]) -> tuple[str, float]:
        """Aggregate votes into a single decision and confidence.

        Returns:
            Tuple of (decision, confidence) where decision is one of
            "approve", "reject", or "abstain".
        """
        if not votes:
            return ("abstain", 0.0)

        weighted = self._weighted_vote(votes)

        if not weighted:
            return ("abstain", 0.0)

        decision = max(weighted, key=weighted.get)
        total_weight = sum(weighted.values())
        confidence = weighted[decision] / total_weight if total_weight > 0 else 0.0

        return (decision, round(confidence, 4))

    def _weighted_vote(self, votes: list[ReviewVote]) -> dict[str, float]:
        """Weight each vote by its confidence score.

        Returns:
            Dict mapping decision string to summed confidence weight.
        """
        weights: dict[str, float] = {}
        for vote in votes:
            d = vote.decision
            if d not in ("approve", "reject", "abstain"):
                d = "abstain"
            weights[d] = weights.get(d, 0.0) + vote.confidence
        return weights
