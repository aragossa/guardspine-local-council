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
| `sanitizer` | `None` | Optional external sanitizer (e.g. PII-Shield client) |
| `sanitization_salt_fingerprint` | `sha256:00000000` | Non-secret salt fingerprint for sanitization attestations |
| `model` | llama3.1 | Ollama model name |
| `base_url` | http://localhost:11434 | Ollama API endpoint |

## Evidence Bundle Output

Council reviews produce v0.2.x evidence bundles containing:
- Individual reviewer votes with confidence scores
- Consensus decision and rationale
- Hash chain with immutability proof
- Optional `sanitization` attestation metadata when a sanitizer is configured

```python
result = await council.review(request)

# Access the evidence bundle
bundle = result.evidence_bundle
print(f"Bundle ID: {bundle['bundle_id']}")
print(f"Root hash: {bundle['immutability_proof']['root_hash']}")

# Verify with guardspine-verify
import json
with open("council-evidence.json", "w") as f:
    json.dump(bundle, f)
# $ guardspine-verify council-evidence.json
```

**Note**: Bundles are unsigned by default. For signed bundles, use GuardSpine Enterprise
or provide a signing key via configuration.

## PII-Shield Integration

guardspine-local-council supports [PII-Shield](https://github.com/aragossa/pii-shield) sanitization to remove secrets and PII from prompts before they reach local AI models.

### Why

Even with local Ollama models, code submitted for review may contain API keys, credentials, or PII. Sanitizing before prompt assembly ensures sensitive data never enters model context, regardless of whether the model is local or cloud-hosted. This is defense-in-depth: if someone later switches to a cloud provider, the sanitization is already in place.

### Where

Sanitization runs in `src/guardspine_local_council/council.py`. Both `review()` and `rubric_review()` (which also covers `full_audit()`) pass artifact content and context through the configured sanitizer before assembling prompts for Ollama models.

### How

```python
from guardspine_local_council import LocalCouncil, OllamaProvider

# Provide any callable that sanitizes text
def my_sanitizer(text: str) -> str:
    # Call PII-Shield API or local entropy detector
    return sanitized_text

council = LocalCouncil(
    providers=[OllamaProvider(model="llama3.1", reviewer_id="r1")],
    sanitizer=my_sanitizer,
    sanitization_salt_fingerprint="sha256:your-org-fingerprint",
)
```

When a sanitizer is configured, evidence bundles produced by council reviews include a `sanitization` attestation block (v0.2.1 format).

## Ollama Requirements

Before running, ensure Ollama is accessible:

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Pull required models
ollama pull llama3.1
ollama pull codellama
```

The council will return abstain votes if a model is unavailable.

## GuardSpine Enterprise

For Byzantine consensus, calibrated voting, and cloud SLAs, see **GuardSpine Enterprise**.

## Related Projects

| Project | Description |
|---------|-------------|
| [guardspine-verify](https://github.com/DNYoussef/guardspine-verify) | Verify council evidence offline |
| [guardspine-spec](https://github.com/DNYoussef/guardspine-spec) | Bundle specification |
| [@guardspine/kernel](https://github.com/DNYoussef/guardspine-kernel) | Canonical hashing |

## License

Apache 2.0
