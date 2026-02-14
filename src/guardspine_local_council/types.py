"""Core data types for guardspine-local-council."""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Any


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
class EvidenceItem:
    """A single item in an evidence bundle."""

    item_id: str
    content_type: str  # "guardspine/council-vote" | "guardspine/council-consensus"
    content: dict[str, Any]
    content_hash: str  # "sha256:..."
    sequence: int


@dataclass
class HashChainLink:
    """A single link in the hash chain."""

    sequence: int
    item_id: str
    content_type: str
    content_hash: str  # "sha256:..."
    previous_hash: str
    chain_hash: str  # "sha256:..."


@dataclass
class ImmutabilityProof:
    """Hash-chain proof for an evidence bundle."""

    hash_chain: list[HashChainLink]
    root_hash: str  # "sha256:..."


@dataclass
class EvidenceBundle:
    """v0.2.0 evidence bundle emitted after council review."""

    bundle_id: str
    version: str  # "0.2.0" | "0.2.1"
    created_at: str  # ISO 8601
    items: list[EvidenceItem]
    immutability_proof: ImmutabilityProof
    sanitization: dict[str, Any] | None = None


@dataclass
class CouncilResult:
    """Aggregated result from all council reviewers."""

    request_id: str
    votes: list[ReviewVote]
    consensus_decision: str
    consensus_confidence: float
    dissenting_opinions: list[ReviewVote]
    quorum_met: bool
    evidence_bundle: Optional[EvidenceBundle] = None


@dataclass
class RubricContext:
    """Context from a deterministic rubric scan to focus an LLM review."""

    rubric_name: str
    description: str
    violations: list[dict] = field(default_factory=list)


@dataclass
class RubricVerdict:
    """Per-rubric aggregated result from 3 model votes."""

    rubric_name: str
    votes: list[ReviewVote]
    decision: str  # "pass" | "fail" | "needs-review"
    critical_findings: list[dict] = field(default_factory=list)


@dataclass
class FileFinding:
    """A single finding attributed to a specific file."""

    rubric: str
    reviewer_id: str
    severity: str
    category: str
    description: str
    line_number: int | str | None = None


@dataclass
class FileReport:
    """All findings for a single file, gathered across all 33 reviews."""

    filename: str
    findings: list[FileFinding] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity in ("critical", "high"))


@dataclass
class AuditResult:
    """Full audit result: 11 rubric verdicts + overall decision."""

    request_id: str
    rubric_verdicts: list[RubricVerdict]
    overall_decision: str  # "approve" | "reject" | "needs-review"
    total_votes: int
    summary: str

    def by_file(self) -> dict[str, FileReport]:
        """Pivot all findings from rubric-oriented to file-oriented view."""
        reports: dict[str, FileReport] = {}
        for verdict in self.rubric_verdicts:
            # Scanner violations (deterministic) are already in critical_findings
            for cf in verdict.critical_findings:
                fname = cf.get("file", "_unknown")
                if fname not in reports:
                    reports[fname] = FileReport(filename=fname)
                reports[fname].findings.append(FileFinding(
                    rubric=verdict.rubric_name,
                    reviewer_id="scanner",
                    severity=cf.get("severity", "unknown"),
                    category=cf.get("category", cf.get("rule_id", "")),
                    description=cf.get("description", ""),
                    line_number=cf.get("line_number"),
                ))
            # LLM findings from each vote
            for vote in verdict.votes:
                for f in vote.findings:
                    fname = f.get("file", "_unknown")
                    if fname not in reports:
                        reports[fname] = FileReport(filename=fname)
                    reports[fname].findings.append(FileFinding(
                        rubric=verdict.rubric_name,
                        reviewer_id=vote.reviewer_id,
                        severity=f.get("severity", "unknown"),
                        category=f.get("category", ""),
                        description=f.get("description", ""),
                        line_number=f.get("line_number"),
                    ))
        return reports
