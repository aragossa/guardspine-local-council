"""Core data types for guardspine-local-council."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReviewRequest:
    """A request to review an artifact."""

    artifact_id: str
    artifact_type: str
    content: str
    context: dict = field(default_factory=dict)
    risk_tier_hint: Optional[str] = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ReviewVote:
    """A single reviewer's vote on an artifact."""

    reviewer_id: str
    decision: str  # "approve" | "reject" | "abstain"
    confidence: float
    rationale: str
    findings: list[dict] = field(default_factory=list)


@dataclass
class CouncilResult:
    """Aggregated result from all council reviewers."""

    request_id: str
    votes: list[ReviewVote]
    consensus_decision: str
    consensus_confidence: float
    dissenting_opinions: list[ReviewVote]
    quorum_met: bool
