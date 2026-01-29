# guardspine-local-council

**Local AI Council -- No API Keys Required**

Run multi-model code review councils entirely on your machine using [Ollama](https://ollama.com). No cloud APIs, no tokens, no data leaves your network.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- At least one model pulled (e.g. `ollama pull llama3.1`)

## Install

```bash
pip install guardspine-local-council
```

Or from source:

```bash
git clone https://github.com/DNYoussef/guardspine-local-council.git
cd guardspine-local-council
pip install -e .
```

## Quick Start

```python
import asyncio
from guardspine_local_council import LocalCouncil, OllamaProvider, ReviewRequest

async def main():
    providers = [
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-a"),
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-b"),
        OllamaProvider(model="llama3.1", reviewer_id="reviewer-c"),
    ]

    council = LocalCouncil(providers, quorum=2, consensus_threshold=0.66)

    request = ReviewRequest(
        artifact_id="my-function",
        artifact_type="python-function",
        content="def add(a, b): return a + b",
    )

    result = await council.review(request)
    print(f"Decision: {result.consensus_decision} ({result.consensus_confidence})")

asyncio.run(main())
```

## How It Works

1. You create multiple `OllamaProvider` instances (same or different models).
2. `LocalCouncil` sends the review prompt to all providers in parallel.
3. Each provider returns a structured vote (approve/reject/abstain + confidence).
4. `SimpleAggregator` computes a confidence-weighted majority decision.
5. Quorum and consensus threshold checks determine the final result.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `quorum` | 3 | Minimum non-abstain votes required |
| `consensus_threshold` | 0.66 | Minimum weighted confidence for a decision |
| `model` | llama3.1 | Ollama model name |
| `base_url` | http://localhost:11434 | Ollama API endpoint |

## GuardSpine Enterprise

For Byzantine consensus, calibrated voting, and cloud SLAs, see **GuardSpine Enterprise**.

## License

Apache 2.0
