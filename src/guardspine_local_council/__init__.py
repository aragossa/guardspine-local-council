"""guardspine-local-council -- Local AI council review using Ollama."""

from .aggregator import SimpleAggregator
from .council import LocalCouncil
from .providers.ollama import OllamaProvider
from .types import AuditResult, CouncilResult, FileFinding, FileReport, ReviewRequest, ReviewVote, RubricContext, RubricVerdict

__all__ = [
    "AuditResult",
    "CouncilResult",
    "FileFinding",
    "FileReport",
    "LocalCouncil",
    "OllamaProvider",
    "ReviewRequest",
    "ReviewVote",
    "RubricContext",
    "RubricVerdict",
    "SimpleAggregator",
]

__version__ = "0.1.0"
