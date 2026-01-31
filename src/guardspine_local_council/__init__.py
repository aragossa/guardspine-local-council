"""guardspine-local-council -- Local AI council review using Ollama."""

from .aggregator import SimpleAggregator
from .council import LocalCouncil
from .providers.anthropic import AnthropicProvider
from .providers.hooks import HookContext, MCPClientHook, ReviewHook, SequentialThinkingHook
from .providers.mcp_client import MCPClient
from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.openrouter import OpenRouterProvider
from .types import AuditResult, CouncilResult, FileFinding, FileReport, ReviewRequest, ReviewVote, RubricContext, RubricVerdict

__all__ = [
    "AnthropicProvider",
    "AuditResult",
    "CouncilResult",
    "FileFinding",
    "FileReport",
    "HookContext",
    "LocalCouncil",
    "MCPClient",
    "MCPClientHook",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "ReviewHook",
    "ReviewRequest",
    "ReviewVote",
    "RubricContext",
    "RubricVerdict",
    "SequentialThinkingHook",
    "SimpleAggregator",
]

__version__ = "0.1.0"
