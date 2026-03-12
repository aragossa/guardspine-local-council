# guardspine-local-council

**Multi-model AI code review council -- local-first, cloud-optional.**

Run multi-model code review councils on your machine using [Ollama](https://ollama.com), or connect to cloud providers (OpenAI, Anthropic, OpenRouter). Reviews produce cryptographically chained evidence bundles compatible with the GuardSpine ecosystem.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`) for local-only use
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

### Dependencies

- **guardspine-kernel** (>=0.2.0) -- Canonical JSON hashing (RFC 8785) and content hash computation. Ensures cross-language parity with the TypeScript `@guardspine/kernel`.
- **httpx** (>=0.24.0) -- Async HTTP client for Ollama and cloud API calls.
- **wasmtime** (>=16.0.0) -- WASM runtime for the built-in PII-Shield sanitizer.

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

1. You create provider instances (Ollama, OpenAI, Anthropic, or OpenRouter).
2. `LocalCouncil` sanitizes the review prompt through the built-in PII-Shield WASM module.
3. The sanitized prompt is sent to all providers in parallel.
4. Each provider returns a structured vote (approve/reject/abstain + confidence + findings).
5. `SimpleAggregator` computes a confidence-weighted majority decision.
6. Quorum and consensus threshold checks determine the final result.
7. An evidence bundle is produced with a SHA-256 hash chain for tamper detection.

## Providers

Four providers are included. All implement the `ReviewProvider` protocol and return `ReviewVote` objects.

### OllamaProvider (local, no API key)

```python
from guardspine_local_council import OllamaProvider

provider = OllamaProvider(
    model="llama3.1",           # Any Ollama model
    base_url="http://localhost:11434",  # Ollama API endpoint
    reviewer_id="local-1",
)
```

Uses Ollama's `/api/generate` endpoint with JSON format mode. Falls back to abstain on parse failure.

### OpenAIProvider

```python
from guardspine_local_council import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-4o",
    api_key="sk-...",  # or set OPENAI_API_KEY env var
)
```

### AnthropicProvider

```python
from guardspine_local_council import AnthropicProvider

provider = AnthropicProvider(
    model="claude-sonnet-4-5-20250929",
    api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY env var
)
```

### OpenRouterProvider

```python
from guardspine_local_council import OpenRouterProvider

provider = OpenRouterProvider(
    model="openrouter/auto",  # or any model on OpenRouter
    api_key="sk-or-...",      # or set OPENROUTER_API_KEY env var
)
```

You can mix providers freely. A council of 1 Ollama + 1 OpenAI + 1 Anthropic model works.

## Council Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `providers` | (required) | List of `ReviewProvider` instances |
| `hooks` | `[]` | Optional list of `ReviewHook` instances for pre/post processing |
| `sanitizer` | `None` | Optional external sanitizer (in addition to built-in WASM) |
| `quorum` | `3` | Minimum non-abstain votes required |
| `consensus_threshold` | `0.66` | Minimum weighted confidence for a decision |
| `sanitization_salt_fingerprint` | `sha256:00000000` | Non-secret salt fingerprint for sanitization attestations |

## Review Modes

### Single Review

`council.review(request)` sends one prompt to all providers in parallel and returns a `CouncilResult` with the aggregated decision.

### Rubric Review

`council.rubric_review(request, rubric)` reviews code against a specific rubric. Providers run sequentially (VRAM constraint for local models). Returns a list of `ReviewVote` objects.

```python
from guardspine_local_council import RubricContext

rubric = RubricContext(
    rubric_name="input-validation",
    description="All user input must be validated before use",
    violations=[  # from a deterministic scanner
        {"severity": "high", "rule_id": "IV-001", "file": "api.py", "line_number": 42,
         "description": "Unvalidated query parameter"}
    ],
)

votes = await council.rubric_review(request, rubric)
```

### Full Audit

`council.full_audit(request, rubrics)` runs all providers against all rubrics and aggregates into an `AuditResult`. Each rubric gets a pass/fail/needs-review verdict via 2-of-3 majority. The overall decision rejects if any rubric with critical findings fails.

```python
result = await council.full_audit(request, rubrics)
print(result.overall_decision)  # "approve" | "reject" | "needs-review"
print(result.summary)

# Pivot findings from rubric-oriented to file-oriented
for filename, report in result.by_file().items():
    print(f"{filename}: {report.critical_count} critical findings")
```

## Hooks

Hooks run deterministically around review calls. The models never call MCP tools themselves -- hooks enrich prompts before the model sees them and validate output after.

### SequentialThinkingHook

Connects to `@modelcontextprotocol/server-sequential-thinking` via stdio. Decomposes each rubric into 5 structured reasoning steps and prepends a chain-of-thought scaffold to the prompt.

```python
from guardspine_local_council import SequentialThinkingHook

hook = SequentialThinkingHook(num_steps=5)

council = LocalCouncil(providers, hooks=[hook])
await council.start_hooks()
result = await council.full_audit(request, rubrics)
await council.close_hooks()
```

### MCPClientHook

Generic hook that calls any MCP server's tool to enrich prompts. Useful for injecting library docs, past findings, or external context.

```python
from guardspine_local_council import MCPClientHook

hook = MCPClientHook(
    name="memory",
    server_command=["python", "-m", "memory_mcp"],
    tool_name="recall",
)
```

## PII-Shield Integration

All review prompts pass through a built-in PII-Shield WASM module (`lib/pii-shield.wasm`) before reaching any model. This strips API keys, credentials, and PII from code submitted for review.

The WASM module runs via `wasmtime` using temporary files for stdin/stdout. The Engine and Module are cached as a singleton; only the Store is recreated per call.

**Fail-closed by default**: if the WASM module fails, the review raises `RuntimeError` rather than sending unsanitized content. Set `GUARDSPINE_PII_FAIL_OPEN=1` to override (not recommended for production).

You can also provide an additional external sanitizer via the `sanitizer` parameter on `LocalCouncil`. Both stages are tracked in the evidence bundle's `sanitization` attestation block.

## Evidence Bundle Output

Council reviews produce v0.2.x evidence bundles containing:

- Individual reviewer votes with confidence scores
- Consensus decision and rationale
- SHA-256 hash chain with immutability proof (using `guardspine-kernel` for canonical JSON hashing)
- Optional `sanitization` attestation metadata (v0.2.1 format when sanitization occurred)

```python
result = await council.review(request)
bundle = result.evidence_bundle

print(f"Bundle ID: {bundle.bundle_id}")
print(f"Version: {bundle.version}")  # "0.2.0" or "0.2.1"
print(f"Root hash: {bundle.immutability_proof.root_hash}")

# Verify with guardspine-verify
import json
with open("council-evidence.json", "w") as f:
    json.dump(bundle.__dict__, f, default=str)
# $ guardspine-verify council-evidence.json
```

Bundles are unsigned by default. For signed bundles, use GuardSpine Enterprise or provide a signing key via configuration.

## Ollama Setup

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Pull models
ollama pull llama3.1
ollama pull codellama
```

The council returns abstain votes if a model is unavailable.

## Data Types

| Type | Purpose |
|------|---------|
| `ReviewRequest` | Input: artifact ID, type, content, optional context and risk tier hint |
| `ReviewVote` | One reviewer's decision (approve/reject/abstain), confidence, rationale, findings |
| `CouncilResult` | Aggregated result with votes, consensus, dissent, quorum status, evidence bundle |
| `RubricContext` | Scanner-produced rubric with name, description, and violations |
| `RubricVerdict` | Per-rubric result: pass/fail/needs-review with critical findings |
| `AuditResult` | Full audit result across all rubrics with overall decision |
| `FileFinding` | Single finding attributed to a specific file (for `by_file()` pivot) |
| `FileReport` | All findings for one file, with `critical_count` property |
| `EvidenceBundle` | v0.2.x bundle with items, hash chain, and optional sanitization |

## Related Projects

| Project | Description |
|---------|-------------|
| [guardspine-kernel-py](https://github.com/DNYoussef/guardspine-kernel-py) | Python kernel: canonical hashing, content hash (required dependency) |
| [@guardspine/kernel](https://github.com/DNYoussef/guardspine-kernel) | TypeScript kernel (cross-language parity) |
| [guardspine-verify](https://github.com/DNYoussef/guardspine-verify) | Verify council evidence bundles offline |
| [guardspine-spec](https://github.com/DNYoussef/guardspine-spec) | Bundle specification (v0.2.1) |
| [codeguard-action](https://github.com/DNYoussef/codeguard-action) | GitHub Action for automated code review |

## License

Apache 2.0
