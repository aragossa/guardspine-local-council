"""Evidence test: run a 3-model council review on guardspine-kernel source."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Add local package to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from guardspine_local_council.council import LocalCouncil
from guardspine_local_council.providers.ollama import OllamaProvider
from guardspine_local_council.types import ReviewRequest


def get_ollama_models() -> list[str]:
    """Return list of installed Ollama model names."""
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
    )
    seen_ids: set[str] = set()
    models = []
    for line in result.stdout.strip().splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 2:
            name, model_id = parts[0], parts[1]
            if model_id not in seen_ids:
                seen_ids.add(model_id)
                models.append(name)
    return models


def read_kernel_source() -> str:
    """Read key kernel source files for review."""
    kernel_dir = Path(r"D:\Projects\guardspine-kernel\src")
    files = ["verify.ts", "canonical.ts", "seal.ts", "errors.ts"]
    parts = []
    for f in files:
        fp = kernel_dir / f
        if fp.exists():
            parts.append(f"--- {f} ---\n{fp.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


async def main() -> None:
    models = get_ollama_models()
    if len(models) < 2:
        print(json.dumps({"error": f"Need 2+ models, found {len(models)}: {models}"}, indent=2))
        sys.exit(1)

    print(f"Council models: {models}", file=sys.stderr)

    providers = [OllamaProvider(model=m) for m in models[:3]]
    council = LocalCouncil(providers=providers, quorum=min(len(providers), 3))

    source = read_kernel_source()
    request = ReviewRequest(
        artifact_id="guardspine-kernel-v1",
        artifact_type="source_code",
        content=source[:8000],  # stay within model context
        context={
            "language": "typescript",
            "purpose": "cryptographic evidence bundle verification",
            "files": ["verify.ts", "canonical.ts", "seal.ts", "errors.ts"],
        },
        risk_tier_hint="high",
    )

    result = await council.review(request)

    output = {
        "request_id": result.request_id,
        "consensus_decision": result.consensus_decision,
        "consensus_confidence": result.consensus_confidence,
        "quorum_met": result.quorum_met,
        "votes": [
            {
                "reviewer_id": v.reviewer_id,
                "decision": v.decision,
                "confidence": v.confidence,
                "rationale": v.rationale,
                "findings": v.findings,
            }
            for v in result.votes
        ],
        "dissenting_count": len(result.dissenting_opinions),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
