"""Evidence test: rubric-aware council (3 models x 11 rubrics = 33 reviews)."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Add local packages to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, r"D:\Projects\GuardSpine")

from guardspine_local_council.council import LocalCouncil
from guardspine_local_council.providers.ollama import OllamaProvider
from guardspine_local_council.types import ReviewRequest, RubricContext

from codeguard.rubrics.loader import load_rubric
from codeguard.rubrics.evaluator import RubricEvaluator

RUBRICS_DIR = Path(r"D:\Projects\GuardSpine\rubrics")
KERNEL_SRC = Path(r"D:\Projects\guardspine-kernel\src")

CODE_QUALITY_RUBRICS = {
    "clarity", "connascence", "mece", "nasa-safety",
    "safety-violations", "six-sigma", "theater-detection",
}


def get_ollama_models() -> list[str]:
    """Return list of installed Ollama model names."""
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
    )
    seen_ids: set[str] = set()
    models = []
    for line in result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            name, model_id = parts[0], parts[1]
            if model_id not in seen_ids:
                seen_ids.add(model_id)
                models.append(name)
    return models


def read_kernel_source() -> str:
    """Read key kernel source files for review."""
    files = ["verify.ts", "canonical.ts", "seal.ts", "errors.ts"]
    parts = []
    for f in files:
        fp = KERNEL_SRC / f
        if fp.exists():
            parts.append(f"--- {f} ---\n{fp.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def run_deterministic_scan(source_files: list[Path]) -> list[RubricContext]:
    """Run all 11 rubric scanners and return RubricContext per rubric."""
    rubric_contexts = []

    for rubric_path in sorted(RUBRICS_DIR.glob("*.yaml")):
        rubric = load_rubric(str(rubric_path))
        evaluator = RubricEvaluator(rubric)

        violations = []
        for tf in source_files:
            try:
                code = tf.read_text(encoding="utf-8")
            except Exception:
                continue
            for v in evaluator.evaluate(code, str(tf)):
                violations.append({
                    "file": tf.name,
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "line_number": v.line_number,
                    "description": v.description[:120],
                })

        rubric_contexts.append(RubricContext(
            rubric_name=rubric_path.stem,
            description=rubric.description if hasattr(rubric, "description") else rubric_path.stem,
            violations=violations[:30],
        ))

    return rubric_contexts


async def main() -> None:
    models = get_ollama_models()
    if len(models) < 2:
        print(json.dumps({"error": f"Need 2+ models, found {len(models)}: {models}"}, indent=2))
        sys.exit(1)

    print(f"Council models: {models[:3]}", file=sys.stderr)

    # Step 1: Collect source files
    source_files = sorted(KERNEL_SRC.glob("*.ts"))
    source_files = [f for f in source_files if not f.name.endswith(".d.ts")]
    print(f"Source files: {[f.name for f in source_files]}", file=sys.stderr)

    # Step 2: Deterministic rubric scan
    print("Running deterministic rubric scan...", file=sys.stderr)
    rubric_contexts = run_deterministic_scan(source_files)
    for rc in rubric_contexts:
        print(f"  {rc.rubric_name}: {len(rc.violations)} violations", file=sys.stderr)

    # Step 3: Build review request
    source = read_kernel_source()
    request = ReviewRequest(
        artifact_id="guardspine-kernel-v1",
        artifact_type="source_code",
        content=source[:8000],
        context={
            "language": "typescript",
            "purpose": "cryptographic evidence bundle verification",
            "files": [f.name for f in source_files],
        },
        risk_tier_hint="high",
    )

    # Step 4: Rubric-aware council audit (3 models x 11 rubrics = 33 reviews)
    providers = [OllamaProvider(model=m) for m in models[:3]]
    council = LocalCouncil(providers=providers, quorum=min(len(providers), 3))

    print(f"\nStarting rubric-aware audit: {len(providers)} models x {len(rubric_contexts)} rubrics = {len(providers) * len(rubric_contexts)} reviews", file=sys.stderr)
    audit = await council.full_audit(request, rubric_contexts)

    # Step 5: Output structured result
    output = {
        "request_id": audit.request_id,
        "overall_decision": audit.overall_decision,
        "total_votes": audit.total_votes,
        "summary": audit.summary,
        "rubric_verdicts": [
            {
                "rubric": v.rubric_name,
                "decision": v.decision,
                "critical_findings_count": len(v.critical_findings),
                "votes": [
                    {
                        "reviewer_id": vote.reviewer_id,
                        "decision": vote.decision,
                        "confidence": vote.confidence,
                        "rationale": vote.rationale[:200],
                        "findings_count": len(vote.findings),
                    }
                    for vote in v.votes
                ],
            }
            for v in audit.rubric_verdicts
        ],
        "by_file": {
            fname: {
                "critical_count": report.critical_count,
                "total_findings": len(report.findings),
                "findings": [
                    {
                        "rubric": f.rubric,
                        "reviewer": f.reviewer_id,
                        "severity": f.severity,
                        "category": f.category,
                        "description": f.description,
                        "line": f.line_number,
                    }
                    for f in sorted(report.findings, key=lambda x: (
                        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 4)
                    ))
                ],
            }
            for fname, report in sorted(
                audit.by_file().items(),
                key=lambda x: x[1].critical_count,
                reverse=True,
            )
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
