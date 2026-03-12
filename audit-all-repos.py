"""Dogfood: run 3-model x 11-rubric council audit on every GuardSpine repo."""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECTS_ROOT = Path(os.environ.get("GUARDSPINE_PROJECTS_ROOT", str(SCRIPT_DIR.parent)))
GUARDSPINE_ROOT = PROJECTS_ROOT / "GuardSpine"

sys.path.insert(0, str(SCRIPT_DIR / "src"))
sys.path.insert(0, str(GUARDSPINE_ROOT))

from guardspine_local_council.council import LocalCouncil
from guardspine_local_council.providers.ollama import OllamaProvider
from guardspine_local_council.providers.hooks import SequentialThinkingHook
from guardspine_local_council.types import ReviewRequest, RubricContext

from codeguard.rubrics.loader import load_rubric
from codeguard.rubrics.evaluator import RubricEvaluator

import subprocess

RUBRICS_DIR = GUARDSPINE_ROOT / "rubrics"
OUTPUT_DIR = SCRIPT_DIR / "evidence-packs"

# All repos to audit (name -> source dir + file extensions)
REPOS = {
    "guardspine-kernel": {
        "src": PROJECTS_ROOT / "guardspine-kernel" / "src",
        "exts": {".ts"},
        "description": "Offline evidence bundle verification with timing-safe comparisons",
        "language": "typescript",
    },
    "guardspine-verify": {
        "src": PROJECTS_ROOT / "guardspine-verify" / "guardspine_verify",
        "exts": {".py"},
        "description": "Offline evidence bundle verification CLI",
        "language": "python",
    },
    "guardspine-spec": {
        "src": PROJECTS_ROOT / "guardspine-spec" / "schemas",
        "exts": {".json"},
        "description": "Evidence bundle specification and JSON schemas",
        "language": "json-schema",
    },
    "guardspine-local-council": {
        "src": SCRIPT_DIR / "src" / "guardspine_local_council",
        "exts": {".py"},
        "description": "Local LLM council for offline artifact review via Ollama",
        "language": "python",
    },
    "guardspine-adapter-webhook": {
        "src": PROJECTS_ROOT / "guardspine-adapter-webhook" / "src",
        "exts": {".ts"},
        "description": "Webhook adapter for evidence bundle delivery",
        "language": "typescript",
    },
    "rlm-docsync": {
        "src": PROJECTS_ROOT / "rlm-docsync" / "src" / "rlm_docsync",
        "exts": {".py"},
        "description": "Self-updating documentation with evidence proofs",
        "language": "python",
    },
    "n8n-nodes-guardspine": {
        "src": PROJECTS_ROOT / "n8n-nodes-guardspine" / "nodes",
        "exts": {".ts"},
        "description": "n8n community nodes for AI governance workflows",
        "language": "typescript",
    },
}


def get_ollama_models() -> list[str]:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
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


def collect_source(src_dir: Path, exts: set[str]) -> tuple[str, list[str]]:
    """Read all source files, return concatenated content and file list."""
    files = []
    for ext in exts:
        files.extend(sorted(src_dir.rglob(f"*{ext}")))
    # Exclude test files and __pycache__
    files = [
        f for f in files
        if "__pycache__" not in str(f)
        and not f.name.endswith(".d.ts")
        and "node_modules" not in str(f)
    ]

    parts = []
    names = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            rel = f.relative_to(src_dir)
            parts.append(f"--- {rel} ---\n{content}")
            names.append(str(rel))
        except Exception:
            continue
    return "\n\n".join(parts), names


def run_deterministic_scan(source_files: list[Path]) -> list[RubricContext]:
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


async def audit_repo(
    repo_name: str,
    repo_config: dict,
    council: LocalCouncil,
    models: list[str],
) -> dict:
    """Run full 33-review audit on one repo."""
    src_dir = repo_config["src"]
    exts = repo_config["exts"]

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"AUDITING: {repo_name}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Collect source
    source_files = []
    for ext in exts:
        source_files.extend(sorted(src_dir.rglob(f"*{ext}")))
    source_files = [
        f for f in source_files
        if "__pycache__" not in str(f)
        and not f.name.endswith(".d.ts")
        and "node_modules" not in str(f)
    ]

    source_text, file_names = collect_source(src_dir, exts)
    if not source_text.strip():
        print(f"  SKIP: no source files found in {src_dir}", file=sys.stderr)
        return {"repo": repo_name, "skipped": True, "reason": "no source files"}

    print(f"  Files: {file_names}", file=sys.stderr)

    # Deterministic scan
    print(f"  Running deterministic rubric scan...", file=sys.stderr)
    rubric_contexts = run_deterministic_scan(source_files)
    for rc in rubric_contexts:
        print(f"    {rc.rubric_name}: {len(rc.violations)} violations", file=sys.stderr)

    # Build request
    request = ReviewRequest(
        artifact_id=f"{repo_name}-audit",
        artifact_type="source_code",
        content=source_text[:12000],
        context={
            "language": repo_config["language"],
            "purpose": repo_config["description"],
            "files": file_names,
        },
        risk_tier_hint="high",
    )

    # Run audit
    n_reviews = len(council.providers) * len(rubric_contexts)
    print(f"  Starting: {len(council.providers)} models x {len(rubric_contexts)} rubrics = {n_reviews} reviews", file=sys.stderr)
    audit = await council.full_audit(request, rubric_contexts)

    # Build evidence pack
    evidence = {
        "meta": {
            "repo": repo_name,
            "description": repo_config["description"],
            "language": repo_config["language"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": models[:3],
            "files_reviewed": file_names,
            "total_reviews": audit.total_votes,
        },
        "request_id": audit.request_id,
        "overall_decision": audit.overall_decision,
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
                        "rationale": vote.rationale[:300],
                        "findings_count": len(vote.findings),
                    }
                    for vote in v.votes
                ],
            }
            for v in audit.rubric_verdicts
        ],
        "by_file": {},
    }

    # File-oriented pivot
    by_file = audit.by_file()
    for fname, report in sorted(by_file.items(), key=lambda x: x[1].critical_count, reverse=True):
        evidence["by_file"][fname] = {
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

    print(f"  DONE: {audit.overall_decision} ({audit.total_votes} votes)", file=sys.stderr)
    return evidence


async def main() -> None:
    models = get_ollama_models()
    if len(models) < 2:
        print(json.dumps({"error": f"Need 2+ models, found {len(models)}: {models}"}, indent=2))
        sys.exit(1)

    models_used = models[:3]
    print(f"Council models: {models_used}", file=sys.stderr)

    # Setup council (hooks disabled for now -- MCP stdio has Windows pipe issues)
    providers = [OllamaProvider(model=m) for m in models_used]
    council = LocalCouncil(providers=providers, quorum=min(len(providers), 3))

    OUTPUT_DIR.mkdir(exist_ok=True)
    all_results = []

    for repo_name, repo_config in REPOS.items():
        try:
            evidence = await audit_repo(repo_name, repo_config, council, models_used)
            all_results.append(evidence)

            # Write individual evidence pack
            out_file = OUTPUT_DIR / f"{repo_name}-evidence.json"
            out_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(f"  Wrote: {out_file}", file=sys.stderr)

        except Exception as exc:
            print(f"  ERROR on {repo_name}: {exc}", file=sys.stderr)
            all_results.append({"repo": repo_name, "error": str(exc)})

    # Write combined summary
    summary_file = OUTPUT_DIR / "audit-summary.json"
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "models": models_used,
        "repos_audited": len(all_results),
        "results": [
            {
                "repo": r.get("repo", r.get("meta", {}).get("repo", "?")),
                "decision": r.get("overall_decision", r.get("error", "skipped")),
                "total_reviews": r.get("meta", {}).get("total_reviews", 0),
            }
            for r in all_results
        ],
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"ALL DONE. {len(all_results)} repos audited.", file=sys.stderr)
    print(f"Evidence packs: {OUTPUT_DIR}", file=sys.stderr)
    print(f"Summary: {summary_file}", file=sys.stderr)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
