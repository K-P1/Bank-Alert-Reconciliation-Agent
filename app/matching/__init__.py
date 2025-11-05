"""Matching engine module exports."""

from app.matching.config import (
    MatchingConfig,
    RuleWeights,
    TimeWindowConfig,
    FuzzyMatchConfig,
    ThresholdConfig,
    CandidateRetrievalConfig,
    TieBreakingConfig,
)

from app.matching.models import (
    RuleScore,
    MatchCandidate,
    MatchResult,
    BatchMatchResult,
)

from app.matching.engine import (
    MatchingEngine,
    match_email,
    match_unmatched,
)

from app.matching.metrics import (
    MatchingMetrics,
    get_metrics,
    reset_metrics,
)

__all__ = [
    # Config
    "MatchingConfig",
    "RuleWeights",
    "TimeWindowConfig",
    "FuzzyMatchConfig",
    "ThresholdConfig",
    "CandidateRetrievalConfig",
    "TieBreakingConfig",
    # Models
    "RuleScore",
    "MatchCandidate",
    "MatchResult",
    "BatchMatchResult",
    # Engine
    "MatchingEngine",
    "match_email",
    "match_unmatched",
    # Metrics
    "MatchingMetrics",
    "get_metrics",
    "reset_metrics",
]
