"""Tests for SimpleAggregator."""

import unittest

from guardspine_local_council.aggregator import SimpleAggregator
from guardspine_local_council.types import ReviewVote


class TestSimpleAggregator(unittest.TestCase):
    def setUp(self):
        self.agg = SimpleAggregator()

    def test_empty_votes(self):
        decision, conf = self.agg.aggregate([])
        self.assertEqual(decision, "abstain")
        self.assertEqual(conf, 0.0)

    def test_unanimous_approve(self):
        votes = [
            ReviewVote("r1", "approve", 0.9, "looks good"),
            ReviewVote("r2", "approve", 0.8, "fine"),
            ReviewVote("r3", "approve", 0.7, "ok"),
        ]
        decision, conf = self.agg.aggregate(votes)
        self.assertEqual(decision, "approve")
        self.assertEqual(conf, 1.0)

    def test_majority_reject(self):
        votes = [
            ReviewVote("r1", "reject", 0.9, "bad"),
            ReviewVote("r2", "reject", 0.8, "issues"),
            ReviewVote("r3", "approve", 0.5, "ok"),
        ]
        decision, conf = self.agg.aggregate(votes)
        self.assertEqual(decision, "reject")
        self.assertGreater(conf, 0.5)

    def test_confidence_weighting(self):
        # One high-confidence approve vs two low-confidence rejects
        votes = [
            ReviewVote("r1", "approve", 0.95, "great"),
            ReviewVote("r2", "reject", 0.1, "maybe"),
            ReviewVote("r3", "reject", 0.1, "unsure"),
        ]
        decision, conf = self.agg.aggregate(votes)
        self.assertEqual(decision, "approve")

    def test_invalid_decision_treated_as_abstain(self):
        votes = [
            ReviewVote("r1", "invalid_value", 0.9, "oops"),
            ReviewVote("r2", "approve", 0.8, "ok"),
        ]
        # invalid_value maps to abstain with weight 0.9, approve has 0.8
        decision, conf = self.agg.aggregate(votes)
        self.assertEqual(decision, "abstain")

    def test_weighted_vote_sums(self):
        votes = [
            ReviewVote("r1", "approve", 0.6, "ok"),
            ReviewVote("r2", "approve", 0.4, "fine"),
        ]
        weights = self.agg._weighted_vote(votes)
        self.assertAlmostEqual(weights["approve"], 1.0)


if __name__ == "__main__":
    unittest.main()
