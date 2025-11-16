"""Configuration for the matching engine.

Match Status Flow:
------------------
1. Scorer determines match quality and returns internal status:
   - "auto_matched"  : Confidence >= 0.80 (auto_match threshold)
   - "needs_review"  : Confidence 0.60-0.79 (needs_review threshold)
   - "rejected"      : Confidence < 0.60 (below reject threshold)
   - "no_candidates" : No matching transactions found

2. Engine maps internal status to database status:
   - "auto_matched"  -> "matched"        (stored in DB)
   - "needs_review"  -> "review"         (stored in DB)
   - "rejected"      -> "rejected"       (stored in DB)
   - "no_candidates" -> "no_candidates"  (stored in DB)
   - unknown         -> "pending"        (fallback)

Database Status Values:
- "matched"        : Auto-accepted match (high confidence >= 0.80)
- "review"         : Needs manual review (medium confidence 0.60-0.79)
- "rejected"       : Auto-rejected (low confidence < 0.60)
- "no_candidates"  : No potential matches found
- "pending"        : Not yet processed or unknown state
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuleWeights(BaseModel):
    """Weights for different matching rules."""

    exact_amount: float = Field(
        default=0.25, ge=0.0, le=1.0, description="Weight for exact amount match"
    )
    exact_reference: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Weight for exact reference match"
    )
    fuzzy_reference: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight for fuzzy reference similarity",
    )
    timestamp_proximity: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Weight for timestamp proximity"
    )
    account_match: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Weight for account number match"
    )
    composite_key: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Weight for composite key match"
    )
    bank_match: float = Field(
        default=0.05, ge=0.0, le=1.0, description="Weight for bank/sender match"
    )

    def total_weight(self) -> float:
        """Calculate total weight (should be close to 1.0).

        Returns:
            Sum of all rule weights
        """
        return (
            self.exact_amount
            + self.exact_reference
            + self.fuzzy_reference
            + self.timestamp_proximity
            + self.account_match
            + self.composite_key
            + self.bank_match
        )


class TimeWindowConfig(BaseModel):
    """Configuration for time window matching."""

    default_hours: int = Field(
        default=48, ge=1, le=720, description="Default time window in hours (±48h)"
    )
    strict_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Strict time window for high-confidence matches",
    )
    max_hours: int = Field(
        default=168,
        ge=1,
        le=720,
        description="Maximum time window to consider (7 days)",
    )


class FuzzyMatchConfig(BaseModel):
    """Configuration for fuzzy string matching."""

    min_similarity: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum similarity to consider"
    )
    high_similarity: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Threshold for high similarity"
    )
    min_token_length: int = Field(
        default=3, ge=1, le=10, description="Minimum token length for matching"
    )
    use_partial_ratio: bool = Field(
        default=True, description="Use partial ratio for substring matching"
    )
    use_token_sort: bool = Field(
        default=True, description="Use token sort ratio for order-independent matching"
    )


class ThresholdConfig(BaseModel):
    """Confidence thresholds for match decisions."""

    auto_match: float = Field(
        default=0.80, ge=0.0, le=1.0, description="Auto-accept threshold"
    )
    needs_review: float = Field(
        default=0.60, ge=0.0, le=1.0, description="Manual review threshold"
    )
    reject: float = Field(
        default=0.40, ge=0.0, le=1.0, description="Auto-reject threshold"
    )

    def validate_thresholds(self) -> None:
        """Ensure thresholds are in correct order.

        Requires: reject < needs_review < auto_match
        Raises ValueError if thresholds are misconfigured.
        """
        if not (self.reject < self.needs_review < self.auto_match):
            raise ValueError(
                "Thresholds must satisfy: reject < needs_review < auto_match"
            )


class CandidateRetrievalConfig(BaseModel):
    """Configuration for candidate retrieval."""

    max_candidates: int = Field(
        default=50, ge=1, le=1000, description="Maximum candidates to retrieve"
    )
    amount_tolerance_percent: float = Field(
        default=0.01, ge=0.0, le=0.1, description="Amount tolerance (1%)"
    )
    require_same_currency: bool = Field(
        default=True, description="Only match same currency"
    )
    exclude_already_matched: bool = Field(
        default=True, description="Exclude already matched transactions"
    )


class TieBreakingConfig(BaseModel):
    """Configuration for tie-breaking when multiple candidates have similar scores."""

    prefer_recent: bool = Field(
        default=True, description="Prefer more recent transactions"
    )
    prefer_high_reference_similarity: bool = Field(
        default=True, description="Prefer higher reference similarity"
    )
    prefer_same_bank: bool = Field(
        default=True, description="Prefer same bank if enrichment available"
    )
    max_tie_difference: float = Field(
        default=0.05, ge=0.0, le=0.2, description="Max score difference to consider tie"
    )


class MatchingConfig(BaseModel):
    """Main configuration for the matching engine."""

    # Sub-configurations
    rule_weights: RuleWeights = Field(default_factory=RuleWeights)
    time_window: TimeWindowConfig = Field(default_factory=TimeWindowConfig)
    fuzzy_match: FuzzyMatchConfig = Field(default_factory=FuzzyMatchConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    candidate_retrieval: CandidateRetrievalConfig = Field(
        default_factory=CandidateRetrievalConfig
    )
    tie_breaking: TieBreakingConfig = Field(default_factory=TieBreakingConfig)

    # General settings
    debug: bool = Field(default=False, description="Enable debug logging")
    store_alternatives: bool = Field(
        default=True, description="Store alternative candidate matches"
    )
    max_alternatives: int = Field(
        default=5, ge=1, le=20, description="Maximum alternative matches to store"
    )

    def validate_config(self) -> None:
        """Validate entire configuration.

        Ensures rule weights sum to approximately 1.0 and thresholds are in correct order.
        Raises ValueError if validation fails.
        """
        self.thresholds.validate_thresholds()

        total_weight = self.rule_weights.total_weight()
        if not (0.95 <= total_weight <= 1.05):
            raise ValueError(f"Rule weights must sum to ~1.0, got {total_weight:.2f}")
