"""Review hooks: pluggable pre/post processing for council review calls.

Hooks run deterministically -- the local models never call MCP tools themselves.
Instead, hooks enrich prompts before the model sees them, and validate output after.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..types import ReviewRequest, ReviewVote, RubricContext
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


@dataclass
class HookContext:
    """Bundled context passed to every hook invocation."""

    request: ReviewRequest
    rubric: RubricContext


@runtime_checkable
class ReviewHook(Protocol):
    """Protocol for hooks that run before/after a review call."""

    name: str

    async def start(self) -> None:
        """Initialize resources (e.g. spawn MCP server). Called once."""
        ...

    async def close(self) -> None:
        """Release resources. Called once when council is done."""
        ...

    async def pre_review(self, prompt: str, context: HookContext) -> str:
        """Return an enriched prompt. Runs once per rubric (before all providers)."""
        ...

    async def post_review(self, vote: ReviewVote, context: HookContext) -> ReviewVote:
        """Return a (possibly modified) vote. Runs once per provider per rubric."""
        ...


class SequentialThinkingHook:
    """Decomposes each rubric review into reasoning steps and injects a scaffold.

    Connects to the @modelcontextprotocol/server-sequential-thinking MCP server
    via stdio. For each rubric, generates 5 structured reasoning steps that get
    prepended to the prompt so the local model sees a chain-of-thought scaffold.
    """

    name = "sequential-thinking"

    def __init__(
        self,
        server_command: list[str] | None = None,
        num_steps: int = 5,
    ) -> None:
        if server_command:
            self._command = server_command
        else:
            # Windows requires npx.cmd for subprocess spawning
            npx = "npx.cmd" if sys.platform == "win32" else "npx"
            self._command = [npx, "-y", "@modelcontextprotocol/server-sequential-thinking"]
        self._num_steps = num_steps
        self._client: MCPClient | None = None

    async def start(self) -> None:
        self._client = MCPClient()
        await self._client.connect(self._command)
        logger.info("SequentialThinkingHook: MCP server started")

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def pre_review(self, prompt: str, context: HookContext) -> str:
        """Build a reasoning scaffold for this rubric and prepend it."""
        rubric = context.rubric
        n_violations = len(rubric.violations)

        # Summarize top violations for the scaffold
        violation_summary = "None found."
        if rubric.violations:
            lines = []
            for v in rubric.violations[:5]:
                lines.append(
                    f"[{v.get('severity', '?')}] {v.get('rule_id', '?')} "
                    f"in {v.get('file', '?')}:{v.get('line_number', '?')}"
                )
            violation_summary = "; ".join(lines)

        steps = self._build_reasoning_steps(
            rubric_name=rubric.rubric_name,
            description=rubric.description,
            n_violations=n_violations,
            violation_summary=violation_summary,
        )

        # Send each step through the sequential-thinking MCP
        thought_texts: list[str] = []
        for i, step_text in enumerate(steps, 1):
            is_last = i == len(steps)
            try:
                result = await self._call_thinking_step(
                    thought=step_text,
                    thought_number=i,
                    total_thoughts=len(steps),
                    next_thought_needed=not is_last,
                )
                thought_texts.append(f"Step {i}: {step_text}")
            except Exception as exc:
                logger.warning("SequentialThinkingHook step %d failed: %s", i, exc)
                thought_texts.append(f"Step {i}: {step_text}")

        scaffold = "\n".join(thought_texts)
        return (
            f"=== REASONING SCAFFOLD ({rubric.rubric_name}) ===\n"
            f"{scaffold}\n"
            f"=== END SCAFFOLD ===\n\n"
            f"{prompt}"
        )

    async def post_review(self, vote: ReviewVote, context: HookContext) -> ReviewVote:
        return vote

    def _build_reasoning_steps(
        self,
        rubric_name: str,
        description: str,
        n_violations: int,
        violation_summary: str,
    ) -> list[str]:
        """Build the reasoning decomposition for a rubric."""
        return [
            (
                f"What does the '{rubric_name}' rubric check for? "
                f"Focus area: {description}. "
                f"I need to identify the specific quality criteria."
            ),
            (
                f"The deterministic scanner found {n_violations} violations: "
                f"{violation_summary}. "
                f"Which of these are likely true positives vs false positives? "
                f"Regex scanners over-report pattern matches without semantic context."
            ),
            (
                f"What could the regex scanner have MISSED for '{rubric_name}'? "
                f"Common blind spots: cross-file dependencies, runtime behavior, "
                f"semantic meaning of variable names, control flow implications."
            ),
            (
                f"For each finding, what is the real-world severity? "
                f"Consider: Is this exploitable? What is the blast radius? "
                f"Could an attacker chain this with other weaknesses?"
            ),
            (
                f"My verdict for '{rubric_name}': based on the true positives "
                f"and missed issues identified above, does this code pass or fail? "
                f"Cite specific evidence for the decision."
            ),
        ]

    async def _call_thinking_step(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        next_thought_needed: bool,
    ) -> dict[str, Any]:
        """Send one thinking step to the MCP server."""
        if not self._client:
            raise RuntimeError("Hook not started -- call start() first")
        return await self._client.call_tool("sequentialthinking", {
            "thought": thought,
            "thoughtNumber": thought_number,
            "totalThoughts": total_thoughts,
            "nextThoughtNeeded": next_thought_needed,
        })


class MCPClientHook:
    """Generic hook that calls any MCP server's tool to enrich prompts.

    Example: inject library docs from context7, or past findings from memory-mcp.
    """

    def __init__(
        self,
        name: str,
        server_command: list[str],
        tool_name: str,
        build_args: Any = None,
        format_result: Any = None,
    ) -> None:
        self.name = name
        self._command = server_command
        self._tool_name = tool_name
        self._build_args = build_args or self._default_build_args
        self._format_result = format_result or self._default_format_result
        self._client: MCPClient | None = None

    async def start(self) -> None:
        self._client = MCPClient()
        await self._client.connect(self._command)
        logger.info("MCPClientHook(%s): MCP server started", self.name)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def pre_review(self, prompt: str, context: HookContext) -> str:
        if not self._client:
            return prompt
        try:
            args = self._build_args(context)
            result = await self._client.call_tool(self._tool_name, args)
            extra = self._format_result(result, context)
            if extra:
                return f"{extra}\n\n{prompt}"
        except Exception as exc:
            logger.warning("MCPClientHook(%s) pre_review failed: %s", self.name, exc)
        return prompt

    async def post_review(self, vote: ReviewVote, context: HookContext) -> ReviewVote:
        return vote

    @staticmethod
    def _default_build_args(context: HookContext) -> dict[str, Any]:
        return {"query": f"{context.rubric.rubric_name}: {context.rubric.description}"}

    @staticmethod
    def _default_format_result(result: Any, context: HookContext) -> str:
        if isinstance(result, dict) and "content" in result:
            items = result["content"]
            if isinstance(items, list):
                texts = [c.get("text", "") for c in items if isinstance(c, dict)]
                return "\n".join(texts)
        return str(result) if result else ""
