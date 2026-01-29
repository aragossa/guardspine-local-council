"""Basic example: run a local council review using Ollama."""

import asyncio

from guardspine_local_council import LocalCouncil, OllamaProvider, ReviewRequest


async def main():
    # Create 3 reviewers using different Ollama models (or the same model).
    # Make sure Ollama is running: ollama serve
    providers = [
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-a"),
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-b"),
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-c"),
    ]

    council = LocalCouncil(providers, quorum=2, consensus_threshold=0.66)

    request = ReviewRequest(
        artifact_id="example-001",
        artifact_type="python-function",
        content="""\
def transfer(amount, from_acct, to_acct):
    from_acct.balance -= amount
    to_acct.balance += amount
    db.commit()
""",
        context={"project": "banking-app", "language": "python"},
        risk_tier_hint="high",
    )

    result = await council.review(request)

    print(f"Decision : {result.consensus_decision}")
    print(f"Confidence: {result.consensus_confidence}")
    print(f"Quorum met: {result.quorum_met}")
    print(f"Votes : {len(result.votes)}")
    for vote in result.votes:
        print(f"  {vote.reviewer_id}: {vote.decision} ({vote.confidence}) - {vote.rationale[:80]}")
    if result.dissenting_opinions:
        print(f"Dissenting: {len(result.dissenting_opinions)}")


if __name__ == "__main__":
    asyncio.run(main())
