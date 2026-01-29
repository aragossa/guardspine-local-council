"""guardspine-local-council -- Local AI council review using Ollama."""

from .aggregator import SimpleAggregator
from .council import LocalCouncil
from .providers.ollama import OllamaProvider
from .types import CouncilResult, ReviewRequest, ReviewVote

__all__ = [
    "CouncilResult",
    "LocalCouncil",
    "OllamaProvider",
    "ReviewRequest",
    "ReviewVote",
    "SimpleAggregator",
]

__version__ = "0.1.0"
